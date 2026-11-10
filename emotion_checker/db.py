import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

from .moods import EXPRESSION_TO_MOOD, MOODS


MOOD_VALUES = ", ".join(repr(mood) for mood in MOODS)
MOOD_CONSTRAINT = f"CHECK (mood IN ({MOOD_VALUES}))"
CHECKIN_TIME_DEFAULT = "DEFAULT (datetime('now', 'localtime'))"
CHECKINS_FIELDS = f"""
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    user_id INTEGER,
    mood TEXT NOT NULL {MOOD_CONSTRAINT},
    note TEXT NOT NULL DEFAULT '',
    is_anonymous INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'MANUAL' CHECK (source IN ('MANUAL', 'AI')),
    confidence REAL,
    device_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL {CHECKIN_TIME_DEFAULT},
    FOREIGN KEY (session_id) REFERENCES class_sessions(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
"""
SESSION_FIELDS = """
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    course_id INTEGER NOT NULL REFERENCES courses(id),
    class_name TEXT NOT NULL DEFAULT '',
    classroom TEXT NOT NULL DEFAULT '',
    session_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    starts_at TEXT NOT NULL,
    ends_at TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
"""

SCHEMA = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
    email TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS class_sessions ({SESSION_FIELDS});

CREATE TABLE IF NOT EXISTS checkins ({CHECKINS_FIELDS});

CREATE TABLE IF NOT EXISTS session_participants (
    session_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, user_id),
    FOREIGN KEY (session_id) REFERENCES class_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    teacher_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, teacher_id),
    FOREIGN KEY (teacher_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_checkins_session_created ON checkins(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_checkins_user_created ON checkins(user_id, created_at);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


@contextmanager
def write_transaction():
    with get_db() as database:
        database.execute("BEGIN IMMEDIATE")
        yield


def init_db():
    database = get_db()
    database.executescript(SCHEMA)
    migrate_schema(database)
    migrate_courses(database)
    seed_demo_data(database)


def migrate_courses(database):
    # Rebuild the parent table in a transaction without triggering child-row cascades.
    database.execute("PRAGMA foreign_keys = OFF")
    try:
        with database:
            database.execute("BEGIN IMMEDIATE")
            database.execute("DROP VIEW IF EXISTS session_details")
            columns = {row[1] for row in database.execute("PRAGMA table_info(class_sessions)")}
            if "course_name" in columns:
                database.execute("""INSERT OR IGNORE INTO courses (name, teacher_id)
                    SELECT DISTINCT course_name, teacher_id FROM class_sessions""")
                database.execute(f"CREATE TABLE class_sessions_new ({SESSION_FIELDS})")
                database.execute("""INSERT INTO sqlite_sequence (name, seq)
                    SELECT 'class_sessions_new', seq FROM sqlite_sequence WHERE name = 'class_sessions'""")
                database.execute("""INSERT INTO class_sessions_new
                    (id, title, course_id, class_name, classroom, session_code, starts_at, ends_at, status, created_at)
                    SELECT s.id, s.title, c.id, s.class_name, s.classroom, s.session_code,
                           s.starts_at, s.ends_at, s.status, s.created_at
                    FROM class_sessions s LEFT JOIN courses c ON c.name = s.course_name AND c.teacher_id = s.teacher_id""")
                database.execute("DROP TABLE class_sessions")
                database.execute("ALTER TABLE class_sessions_new RENAME TO class_sessions")
                if database.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise sqlite3.IntegrityError("Course migration produced an invalid foreign key")
            database.execute("CREATE INDEX IF NOT EXISTS idx_class_sessions_course ON class_sessions(course_id)")
            database.execute("""CREATE VIEW session_details AS
                SELECT s.*, c.name AS course_name, c.teacher_id,
                       CASE WHEN s.status = 'open' AND s.starts_at > datetime('now', 'localtime')
                            THEN 'scheduled' ELSE s.status END AS phase FROM class_sessions s
                JOIN courses c ON c.id = s.course_id""")
    finally:
        database.execute("PRAGMA foreign_keys = ON")


def migrate_schema(database):
    """Upgrade existing databases while preserving their records."""
    user_columns = {row[1] for row in database.execute("PRAGMA table_info(users)")}
    if "email" not in user_columns:
        database.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")

    # The original release used the session title as the only class label.
    # Keep that data intact while exposing explicit class and room fields for
    # the guidebook's ClassSession model.  Both migrations are additive and
    # safe to run repeatedly against an existing local database.
    session_columns = {row[1] for row in database.execute("PRAGMA table_info(class_sessions)")}
    if "class_name" not in session_columns:
        database.execute("ALTER TABLE class_sessions ADD COLUMN class_name TEXT NOT NULL DEFAULT ''")
    if "classroom" not in session_columns:
        database.execute("ALTER TABLE class_sessions ADD COLUMN classroom TEXT NOT NULL DEFAULT ''")
    database.execute(
        "UPDATE class_sessions SET class_name = title WHERE TRIM(class_name) = ''"
    )

    checkin_columns = {row[1] for row in database.execute("PRAGMA table_info(checkins)")}
    for name, sql in (
        ("source", "ALTER TABLE checkins ADD COLUMN source TEXT NOT NULL DEFAULT 'MANUAL'"),
        ("confidence", "ALTER TABLE checkins ADD COLUMN confidence REAL"),
        ("device_id", "ALTER TABLE checkins ADD COLUMN device_id TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in checkin_columns:
            database.execute(sql)

    # Rebuild to update the check-in constraints and timestamp default.
    checkins_sql = database.execute("SELECT sql FROM sqlite_master WHERE name = 'checkins'").fetchone()[0]
    user_id_info = next(row for row in database.execute("PRAGMA table_info(checkins)") if row[1] == "user_id")
    if MOOD_CONSTRAINT not in checkins_sql or CHECKIN_TIME_DEFAULT not in checkins_sql or user_id_info[3]:
        database.execute(f"CREATE TABLE checkins_new ({CHECKINS_FIELDS})")
        database.execute("""INSERT INTO sqlite_sequence (name, seq)
            SELECT 'checkins_new', seq FROM sqlite_sequence WHERE name = 'checkins'""")
        # Early AI records may contain an unmapped model label.
        mood_cases = " ".join("WHEN ? THEN ?" for _ in EXPRESSION_TO_MOOD)
        database.execute(
            f"""INSERT INTO checkins_new
                (id, session_id, user_id, mood, note, is_anonymous, source, confidence, device_id, created_at)
                SELECT id, session_id, user_id, CASE mood {mood_cases} ELSE mood END, note, is_anonymous,
                       COALESCE(source, 'MANUAL'), confidence, COALESCE(device_id, ''), created_at
                FROM checkins""",
            tuple(label for pair in EXPRESSION_TO_MOOD.items() for label in pair),
        )
        database.execute("DROP TABLE checkins")
        database.execute("ALTER TABLE checkins_new RENAME TO checkins")
        database.execute("CREATE INDEX IF NOT EXISTS idx_checkins_session_created ON checkins(session_id, created_at)")
        database.execute("CREATE INDEX IF NOT EXISTS idx_checkins_user_created ON checkins(user_id, created_at)")
    database.commit()


def seed_demo_data(database):
    if database.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return

    users = [
        ("admin", "系统管理员", generate_password_hash("Admin123!"), "admin"),
        ("teacher", "丁老师", generate_password_hash("Teacher123!"), "teacher"),
        ("student", "演示学生", generate_password_hash("Student123!"), "student"),
    ]
    database.executemany(
        "INSERT INTO users (username, display_name, password_hash, role) VALUES (?, ?, ?, ?)",
        users,
    )
    teacher_id = database.execute("SELECT id FROM users WHERE username = 'teacher'").fetchone()[0]
    student_id = database.execute("SELECT id FROM users WHERE username = 'student'").fetchone()[0]
    now = datetime.now().replace(microsecond=0)
    course_id = database.execute(
        "INSERT INTO courses (name, teacher_id) VALUES (?, ?)", ("软件工程实践", teacher_id),
    ).lastrowid
    session_id = database.execute(
        """INSERT INTO class_sessions
           (title, course_id, session_code, starts_at, status)
           VALUES (?, ?, ?, ?, 'open')""",
        ("需求分析与用例", course_id, "SE2026", now.isoformat(" ")),
    ).lastrowid
    database.execute(
        "INSERT INTO session_participants (session_id, user_id) VALUES (?, ?)",
        (session_id, student_id),
    )
    samples = [
        ("calm", "节奏合适", 0, now - timedelta(minutes=26)),
        ("confused", "用例关系还需要一个例子", 1, now - timedelta(minutes=18)),
        ("happy", "小组讨论很有帮助", 0, now - timedelta(minutes=9)),
    ]
    database.executemany(
        """INSERT INTO checkins (session_id, user_id, mood, note, is_anonymous, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(session_id, student_id, mood, note, anonymous, at.isoformat(" ")) for mood, note, anonymous, at in samples],
    )
    database.commit()


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Database initialized.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)

