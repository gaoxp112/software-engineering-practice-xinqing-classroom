import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "instance" / "emotion_checker.sqlite3"
SEED = 20261025


def main():
    sys.path.insert(0, str(ROOT))
    from emotion_checker import create_app
    from emotion_checker.repository import course_id

    create_app({"DATABASE": str(DATABASE)})
    random.seed(SEED)
    database = sqlite3.connect(DATABASE)
    database.execute("PRAGMA foreign_keys = ON")

    if database.execute(
        "SELECT COUNT(*) FROM class_sessions WHERE session_code LIKE 'SMP20%'"
    ).fetchone()[0]:
        raise SystemExit("扩展课堂已存在，未重复写入。")

    teachers = {
        username: user_id
        for user_id, username in database.execute(
            "SELECT id, username FROM users WHERE username IN (?, ?, ?)",
            ("teacher", "sample_teacher1", "sample_teacher2"),
        )
    }
    if len(teachers) != 3:
        raise SystemExit("找不到演示教师账号。请先运行 seed_sample_data.py。")

    students = [row[0] for row in database.execute(
        """SELECT id FROM users
           WHERE role = 'student' AND (username = 'student' OR username LIKE 'sample_student%')
           ORDER BY username"""
    )]
    if len(students) < 2:
        raise SystemExit("找不到样例学生账号。")

    now = datetime.now().replace(microsecond=0)
    session_specs = [
        ("课堂互动与需求分析", "SMP201", "teacher"),
        ("原型评审与用户故事", "SMP202", "teacher"),
        ("面向对象分析", "SMP203", "sample_teacher1"),
        ("设计模式实践", "SMP204", "sample_teacher1"),
        ("质量保障与测试", "SMP205", "sample_teacher2"),
        ("迭代复盘与项目展示", "SMP206", "sample_teacher2"),
    ]
    session_ids = []
    for index, (title, code, teacher_username) in enumerate(session_specs):
        starts_at = now - timedelta(hours=2 + index)
        cursor = database.execute(
            """INSERT INTO class_sessions
               (title, course_id, session_code, starts_at, status)
               VALUES (?, ?, ?, ?, 'open')""",
            (title, course_id(database, "软件工程实践", teachers[teacher_username]), code, starts_at.isoformat(" ")),
        )
        session_ids.append(cursor.lastrowid)

    moods = ["happy", "calm", "confused", "tired", "anxious", "distracted"]
    notes = [
        "讨论环节很有帮助", "希望再看一个具体例子", "目前节奏合适",
        "想进一步确认实践要求", "这个知识点已经理解", "后半段信息量有点大",
    ]
    participant_links = 0
    checkins = 0

    # Make every student see the same set of open sample classrooms.
    open_session_ids = [row[0] for row in database.execute(
        "SELECT id FROM class_sessions WHERE status = 'open'"
    )]
    for session_id in open_session_ids:
        for student_id in students:
            cursor = database.execute(
                "INSERT OR IGNORE INTO session_participants (session_id, user_id) VALUES (?, ?)",
                (session_id, student_id),
            )
            participant_links += cursor.rowcount

    for session_id in session_ids:
        for student_id in students:
            database.execute(
                """INSERT INTO checkins (session_id, user_id, mood, note, is_anonymous, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    student_id,
                    random.choice(moods),
                    random.choice(notes),
                    int(random.random() < 0.25),
                    (now - timedelta(minutes=random.randint(1, 90))).isoformat(" "),
                ),
            )
            checkins += 1

    database.commit()
    teacher_session_counts = {
        username: count
        for username, count in database.execute(
            """SELECT u.username, COUNT(s.id) FROM users u
               LEFT JOIN session_details s ON s.teacher_id = u.id AND s.status = 'open'
               WHERE u.username IN (?, ?, ?) GROUP BY u.id""",
            ("teacher", "sample_teacher1", "sample_teacher2"),
        )
    }
    student_session_counts = {
        username: count
        for username, count in database.execute(
            """SELECT u.username, COUNT(sp.session_id) FROM users u
               LEFT JOIN session_participants sp ON sp.user_id = u.id
               LEFT JOIN class_sessions s ON s.id = sp.session_id AND s.status = 'open'
               WHERE u.role = 'student' AND (u.username = 'student' OR u.username LIKE 'sample_student%')
               GROUP BY u.id"""
        )
    }
    database.close()

    print({
        "open_classrooms_added": len(session_ids),
        "participant_links_added": participant_links,
        "checkins_added": checkins,
        "open_classrooms_per_teacher": teacher_session_counts,
        "open_classrooms_per_student_min": min(student_session_counts.values()),
        "open_classrooms_per_student_max": max(student_session_counts.values()),
        "class_codes": [code for _title, code, _teacher in session_specs],
    })


if __name__ == "__main__":
    main()
