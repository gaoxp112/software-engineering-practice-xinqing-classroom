import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from emotion_checker import create_app
from emotion_checker.db import SCHEMA, SESSION_FIELDS, get_db


class CourseMigrationTest(unittest.TestCase):
    def test_migration_links_same_named_courses_by_teacher_and_preserves_children(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "legacy.sqlite3")
            legacy_fields = SESSION_FIELDS.replace(
                "course_id INTEGER NOT NULL REFERENCES courses(id)",
                "course_name TEXT NOT NULL, teacher_id INTEGER NOT NULL REFERENCES users(id)",
            )
            with closing(sqlite3.connect(path)) as database:
                database.executescript(SCHEMA.replace(SESSION_FIELDS, legacy_fields))
                with database:
                    database.executemany(
                        "INSERT INTO users (id, username, display_name, password_hash, role) VALUES (?, ?, ?, 'hash', ?)",
                        [(1, "first", "教师甲", "teacher"), (2, "second", "教师乙", "teacher"),
                         (3, "student", "学生", "student")],
                    )
                    database.execute("INSERT INTO courses (id, name, teacher_id) VALUES (4, '同名课程', 1)")
                    database.executemany(
                        """INSERT INTO class_sessions (id, title, course_name, teacher_id, session_code, starts_at)
                           VALUES (?, ?, '同名课程', ?, ?, '2026-10-24 10:00:00')""",
                        [(7, "课堂一", 1, "ONE"), (9, "课堂二", 2, "TWO"), (11, "课堂三", 1, "THREE")],
                    )
                    database.execute("INSERT INTO session_participants (session_id, user_id) VALUES (9, 3)")
                    database.execute("INSERT INTO checkins (session_id, user_id, mood) VALUES (9, 3, 'happy')")

            create_app({"DATABASE": path})
            app = create_app({"DATABASE": path})
            with app.app_context():
                database = get_db()
                sessions = database.execute(
                    "SELECT id, course_id, course_name, teacher_id FROM session_details ORDER BY id"
                ).fetchall()
                self.assertEqual([(r["id"], r["teacher_id"]) for r in sessions], [(7, 1), (9, 2), (11, 1)])
                self.assertEqual(sessions[0]["course_id"], 4)
                self.assertEqual(sessions[2]["course_id"], 4)
                self.assertNotEqual(sessions[1]["course_id"], 4)
                self.assertTrue(all(r["course_name"] == "同名课程" for r in sessions))
                self.assertEqual(database.execute("SELECT session_id FROM checkins").fetchone()[0], 9)
                self.assertEqual(database.execute("SELECT session_id FROM session_participants").fetchone()[0], 9)
                self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])
                with self.assertRaises(sqlite3.IntegrityError):
                    database.execute("UPDATE class_sessions SET course_id = -1 WHERE id = 9")
