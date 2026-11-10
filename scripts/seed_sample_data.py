import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "instance" / "emotion_checker.sqlite3"
PASSWORD = "Demo123!"
SEED = 20261024


def main():
    sys.path.insert(0, str(ROOT))
    from emotion_checker import create_app
    from emotion_checker.repository import course_id

    create_app({"DATABASE": str(DATABASE)})
    random.seed(SEED)
    database = sqlite3.connect(DATABASE)
    database.execute("PRAGMA foreign_keys = ON")

    existing = database.execute(
        "SELECT COUNT(*) FROM users WHERE username LIKE 'sample_%'"
    ).fetchone()[0]
    if existing:
        raise SystemExit("样例数据已经存在，未重复写入。")

    now = datetime.now().replace(microsecond=0)
    password_hash = generate_password_hash(PASSWORD)
    teachers = [
        ("sample_teacher1", "陈老师", password_hash, "teacher"),
        ("sample_teacher2", "林老师", password_hash, "teacher"),
    ]
    student_names = [
        "王晨", "李悦", "张宁", "刘思远", "赵安", "周可", "吴桐", "孙晓雨",
        "郑一帆", "何嘉", "高然", "罗欣",
    ]
    students = [
        (f"sample_student{index:02d}", name, password_hash, "student")
        for index, name in enumerate(student_names, start=1)
    ]
    database.executemany(
        "INSERT INTO users (username, display_name, password_hash, role) VALUES (?, ?, ?, ?)",
        teachers + students,
    )

    teacher_ids = [
        row[0] for row in database.execute(
            "SELECT id FROM users WHERE username LIKE 'sample_teacher%' ORDER BY username"
        ).fetchall()
    ]
    student_ids = [
        row[0] for row in database.execute(
            "SELECT id FROM users WHERE username LIKE 'sample_student%' ORDER BY username"
        ).fetchall()
    ]

    session_specs = [
        ("需求访谈与原型评审", "软件工程实践", "SMP101", 0, 2, "open"),
        ("用例建模", "软件工程实践", "SMP102", 1, 2, "closed"),
        ("软件架构设计", "软件工程实践", "SMP103", 0, 4, "closed"),
        ("数据库设计", "软件工程实践", "SMP104", 1, 6, "closed"),
        ("软件测试方法", "软件工程实践", "SMP105", 0, 9, "closed"),
        ("持续集成与交付", "软件工程实践", "SMP106", 1, 12, "closed"),
    ]
    session_ids = []
    session_times = {}
    for title, course, code, teacher_index, days_ago, status in session_specs:
        starts_at = now - timedelta(days=days_ago, hours=2)
        ends_at = None if status == "open" else starts_at + timedelta(hours=2)
        cursor = database.execute(
            """INSERT INTO class_sessions
               (title, course_id, session_code, starts_at, ends_at, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                title, course_id(database, course, teacher_ids[teacher_index]), code, starts_at.isoformat(" "),
                ends_at.isoformat(" ") if ends_at else None, status,
            ),
        )
        session_ids.append(cursor.lastrowid)
        session_times[cursor.lastrowid] = starts_at

    moods = ["happy", "calm", "confused", "tired", "anxious", "distracted"]
    mood_weights = [28, 30, 16, 10, 9, 7]
    notes = {
        "happy": ["小组讨论很有帮助", "示例很清楚", "已经理解这个知识点"],
        "calm": ["节奏合适", "内容可以跟上", "暂时没有问题"],
        "confused": ["希望再讲一个例子", "这里的关系还不太清楚", "需要回顾前置知识"],
        "tired": ["信息量有点大", "后半段注意力下降", "需要短暂休息"],
        "anxious": ["担心实践任务来不及", "不确定作业要求", "希望明确验收标准"],
        "distracted": ["刚才有一段没跟上", "环境有些干扰", "需要重新集中注意力"],
    }

    participant_count = 0
    checkin_count = 0
    for session_id in session_ids:
        selected_students = random.sample(student_ids, random.randint(8, len(student_ids)))
        database.executemany(
            "INSERT INTO session_participants (session_id, user_id) VALUES (?, ?)",
            [(session_id, student_id) for student_id in selected_students],
        )
        participant_count += len(selected_students)
        starts_at = session_times[session_id]
        for student_id in selected_students:
            for _ in range(random.randint(1, 3)):
                mood = random.choices(moods, weights=mood_weights, k=1)[0]
                created_at = starts_at + timedelta(minutes=random.randint(5, 110))
                note = random.choice(notes[mood]) if random.random() < 0.62 else ""
                database.execute(
                    """INSERT INTO checkins
                       (session_id, user_id, mood, note, is_anonymous, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        session_id, student_id, mood, note, int(random.random() < 0.25),
                        created_at.isoformat(" "),
                    ),
                )
                checkin_count += 1

    database.commit()
    database.close()
    print({
        "teachers_added": len(teachers),
        "students_added": len(students),
        "sessions_added": len(session_ids),
        "participant_links_added": participant_count,
        "checkins_added": checkin_count,
        "sample_password": PASSWORD,
    })


if __name__ == "__main__":
    main()
