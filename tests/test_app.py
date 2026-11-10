import csv
import io
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta

from emotion_checker import create_app
from emotion_checker.db import get_db
from emotion_checker.repository import create_ai_checkin
from werkzeug.security import generate_password_hash


class EmotionCheckerTestCase(unittest.TestCase):
    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self.db_file.close()
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": self.db_file.name,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.db_file.name)

    def csrf(self):
        with self.client.session_transaction() as session:
            token = session.get("csrf_token")
        if token is None:
            self.client.get("/login")
            with self.client.session_transaction() as session:
                token = session["csrf_token"]
        return token

    def login(self, username, password):
        response = self.client.post("/login", data={
            "username": username,
            "password": password,
            "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        return response

    def clear_session(self):
        with self.client.session_transaction() as session:
            session.clear()

    def test_health_and_student_login(self):
        self.assertEqual(self.client.get("/health").json["status"], "ok")
        response = self.login("student", "Student123!")
        self.assertIn("进行中的课堂".encode(), response.data)

    def test_student_can_join_and_submit_anonymous_checkin(self):
        self.login("student", "Student123!")
        response = self.client.post("/join", data={
            "session_code": "SE2026", "csrf_token": self.csrf(),
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        response = self.client.post("/checkin/1", data={
            "mood": "confused",
            "note": "这个例子还需要再讲一次",
            "is_anonymous": "1",
            "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("情绪足迹".encode(), response.data)
        with self.app.app_context():
            row = get_db().execute("SELECT mood, is_anonymous FROM checkins ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual((row["mood"], row["is_anonymous"]), ("confused", 1))

    def test_teacher_creates_session_and_exports_anonymous_name(self):
        self.login("teacher", "Teacher123!")
        response = self.client.post("/teacher/sessions", data={
            "course_name": "软件工程实践", "title": "课堂反馈",
            "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("课堂管理".encode(), response.data)
        with self.app.app_context():
            session_id = get_db().execute("SELECT id FROM class_sessions ORDER BY id DESC LIMIT 1").fetchone()[0]
        response = self.client.get(f"/teacher/sessions/{session_id}/export")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))

    def test_teacher_cannot_access_another_teachers_session(self):
        with self.app.app_context():
            database = get_db()
            database.execute(
                """INSERT INTO users (username, display_name, password_hash, role)
                   VALUES ('teacher2', '另一位教师', ?, 'teacher')""",
                (generate_password_hash("Teacher234!"),),
            )
            teacher_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]
            course_id = database.execute(
                "INSERT INTO courses (name, teacher_id) VALUES ('软件工程实践', ?)", (teacher_id,),
            ).lastrowid
            database.execute(
                """INSERT INTO class_sessions
                   (title, course_id, session_code, starts_at)
                   VALUES ('其他课堂', ?, 'OTHER1', ?)""",
                (course_id, datetime.now().replace(microsecond=0).isoformat(" ")),
            )
            session_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]
            database.commit()
        self.login("teacher", "Teacher123!")
        self.assertEqual(self.client.get(f"/teacher/sessions/{session_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/teacher/sessions/{session_id}/summary").status_code, 404)
        self.assertEqual(self.client.get(f"/teacher/sessions/{session_id}/export").status_code, 404)
        self.assertEqual(self.client.get(f"/teacher/sessions/{session_id}/records").status_code, 404)

    def test_teacher_can_schedule_an_owned_classroom(self):
        future = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.login("teacher", "Teacher123!")
        response = self.client.post("/teacher/sessions", data={
            "csrf_token": self.csrf(), "title": "教师自主预约", "course_name": "软件工程实践",
            "starts_at": future, "teacher_id": "999",
        }, follow_redirects=True)
        self.assertIn("课堂已预约".encode(), response.data)
        self.assertIn("待开始".encode(), response.data)
        with self.app.app_context():
            row = get_db().execute(
                """SELECT s.starts_at, s.phase, u.username FROM session_details s
                   JOIN users u ON u.id = s.teacher_id WHERE s.title = ?""", ("教师自主预约",),
            ).fetchone()
            self.assertEqual(tuple(row), (future.replace("T", " ") + ":00", "scheduled", "teacher"))

    def test_student_cannot_access_admin(self):
        self.login("student", "Student123!")
        self.assertEqual(self.client.get("/admin/").status_code, 403)

    def test_admin_can_filter_and_export(self):
        self.login("admin", "Admin123!")
        response = self.client.get("/admin/records?mood=happy")
        self.assertEqual(response.status_code, 200)
        self.assertIn("情绪数据".encode(), response.data)
        response = self.client.get("/admin/records/export?mood=happy")
        self.assertEqual(response.status_code, 200)
        list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))

    def test_csrf_and_closed_session_are_enforced(self):
        self.login("student", "Student123!")
        self.assertEqual(self.client.post("/join", data={"session_code": "SE2026"}).status_code, 400)
        with self.app.app_context():
            database = get_db()
            database.execute("UPDATE class_sessions SET status = 'closed' WHERE id = 1")
            database.commit()
        response = self.client.post("/checkin/1", data={
            "mood": "happy", "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn("课堂已结束".encode(), response.data)

    def test_admin_can_correct_user_creation_errors_in_place(self):
        self.login("admin", "Admin123!")
        form = {"csrf_token": self.csrf(), "display_name": "小明", "role": "student",
                "username": "小明", "password": "Example123!"}
        response = self.client.post("/admin/users/create", data=form)
        self.assertEqual(response.status_code, 400)
        page = response.get_data(as_text=True)
        self.assertIn('role="alert">用户名需为 3-24 位', page)
        self.assertIn('value="小明"', page)
        self.assertNotIn(form["password"], page)

        form["username"] = "xiaoming"
        response = self.client.post("/admin/users/create", data=form, follow_redirects=True)
        self.assertIn("用户已创建。", response.get_data(as_text=True))
        search = self.client.get("/admin/users", query_string={"q": "小明"}).get_data(as_text=True)
        self.assertIn("<strong>小明</strong>", search)
        self.assertIn("@xiaoming", search)

    def test_admin_creates_user_and_manages_participants(self):
        self.login("admin", "Admin123!")
        response = self.client.post("/admin/users/create", data={
            "username": "student2", "display_name": "第二位学生", "password": "Student234!",
            "role": "student", "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn("用户已创建".encode(), response.data)
        with self.app.app_context():
            user_id = get_db().execute("SELECT id FROM users WHERE username = 'student2'").fetchone()[0]
        response = self.client.post("/admin/sessions/1/participants", data={
            "user_ids": [str(user_id)], "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn("课堂参与名单已更新".encode(), response.data)
        with self.app.app_context():
            rows = get_db().execute("SELECT user_id FROM session_participants WHERE session_id = 1").fetchall()
            self.assertEqual([row["user_id"] for row in rows], [user_id])

    def test_teacher_summary_and_date_filters(self):
        self.login("teacher", "Teacher123!")
        response = self.client.get("/teacher/sessions/1/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total"], 3)
        self.clear_session()
        self.login("admin", "Admin123!")
        response = self.client.get("/admin/?start=2026-01-01&end=2026-01-02")
        self.assertEqual(response.status_code, 200)
        self.assertIn("共 0 次".encode(), response.data)

    def test_admin_overview_filters_course_class_and_time_together(self):
        today = datetime.now().date().isoformat()
        with self.app.app_context():
            database = get_db()
            teacher = database.execute("SELECT teacher_id FROM courses WHERE id = 1").fetchone()[0]
            other = database.execute("INSERT INTO courses(name, teacher_id) VALUES ('另一门课程', ?)", (teacher,)).lastrowid
            for code, course, classroom in (("A01", 1, "目标班"), ("A02", 1, "其他班"), ("A03", other, "目标班")):
                session_id = database.execute(
                    """INSERT INTO class_sessions(title, course_id, class_name, session_code, starts_at)
                       VALUES (?, ?, ?, ?, ?)""", (code, course, classroom, code, today + " 08:00:00"),
                ).lastrowid
                database.execute("INSERT INTO checkins(session_id, mood, created_at) VALUES (?, 'happy', ?)",
                                 (session_id, today + " 09:30:00"))
                database.execute("INSERT INTO checkins(session_id, mood, created_at) VALUES (?, 'tired', '2001-01-01 09:30:00')",
                                 (session_id,))
            database.commit()
        self.login("admin", "Admin123!")
        filters = {"course_id": 1, "class_name": "目标班", "start": today, "end": today}
        page = self.client.get("/admin/", query_string=filters).get_data(as_text=True)
        chart = json.loads(re.search(r'id="chart-data">(.*?)</script>', page).group(1))
        self.assertEqual(sum(chart["counts"]), 1)
        self.assertEqual(sum(chart["trend"]["happy"]), 1)
        self.assertEqual(sum(chart["trend"]["tired"]), 0)
        self.assertIn("A01", page)
        self.assertNotIn("A02", page)
        report = self.client.get("/admin/records/export", query_string=filters).get_data(as_text=True)
        self.assertIn("A01", report)
        self.assertNotIn("A03", report)

    def test_admin_schedules_class_and_roster_before_opening_time(self):
        future = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        self.login("admin", "Admin123!")
        with self.app.app_context():
            database = get_db()
            teacher_id = database.execute("SELECT id FROM users WHERE role='teacher'").fetchone()[0]
            student_id = database.execute("SELECT id FROM users WHERE role='student'").fetchone()[0]
        response = self.client.post("/admin/sessions", data={"csrf_token": self.csrf(), "title": "预约课堂样例",
                                    "course_name": "软件工程实践", "teacher_id": teacher_id, "starts_at": future})
        self.assertEqual(response.status_code, 302)
        roster_url = response.headers["Location"]
        session_id = int(roster_url.split("/")[-2])
        shifted = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(roster_url, data={"csrf_token": self.csrf(), "user_ids": [student_id], "starts_at": shifted})
        self.assertEqual(response.status_code, 302)
        self.assertIn(shifted, self.client.get(roster_url).get_data(as_text=True))
        self.clear_session()
        dashboard = self.login("student", "Student123!").get_data(as_text=True)
        self.assertIn("即将开始", dashboard)
        self.assertIn("预约课堂样例", dashboard)
        self.assertNotIn(session_id, [item["id"] for item in self.client.get("/api/sessions").json["data"]["sessions"]])
        response = self.client.post("/api/emoji", json={"session_id": session_id, "mood": "happy"})
        self.assertEqual(response.json["error"]["code"], "SESSION_NOT_STARTED")
        with self.app.app_context():
            database = get_db()
            database.execute("UPDATE class_sessions SET starts_at = datetime('now', 'localtime', '-1 second') WHERE id=?", (session_id,))
            database.commit()
        self.assertIn(session_id, [item["id"] for item in self.client.get("/api/sessions").json["data"]["sessions"]])
        self.assertEqual(self.client.post("/api/emoji", json={"session_id": session_id, "mood": "happy"}).status_code, 201)

    def test_teacher_history_student_filter_keeps_anonymous_feedback_private(self):
        with self.app.app_context():
            database = get_db()
            student_id = database.execute("SELECT id FROM users WHERE role='student'").fetchone()[0]
            database.executemany(
                """INSERT INTO checkins(session_id, user_id, mood, note, is_anonymous, created_at)
                   VALUES (1, ?, 'calm', ?, ?, ?)""",
                [(student_id, "实名反馈样例", 0, "2026-10-10 10:00:45"),
                 (student_id, "匿名反馈样例", 1, "2026-10-10 10:00:50"),
                 (student_id, "时间段外样例", 0, "2026-10-10 10:01:00")],
            )
            database.commit()
        self.login("teacher", "Teacher123!")
        url = "/teacher/sessions/1/records"
        date_range = {"start": "2026-10-10T10:00", "end": "2026-10-10T10:00"}
        all_records = self.client.get(url, query_string=date_range).get_data(as_text=True)
        self.assertIn("匿名同学", all_records)
        self.assertIn("匿名反馈样例", all_records)
        selected = self.client.get(url, query_string={**date_range, "student_id": student_id}).get_data(as_text=True)
        self.assertIn("实名反馈样例", selected)
        self.assertNotIn("匿名反馈样例", selected)
        self.assertNotIn("时间段外样例", selected)

    def test_recent_feedback_orders_manual_and_ai_by_local_time(self):
        before_submit = datetime.now().replace(microsecond=0)
        with self.app.app_context():
            database = get_db()
            sampled_at = (before_submit - timedelta(seconds=30)).isoformat(" ")
            create_ai_checkin(1, "happy", 0.9, "live-webcam", sampled_at)
            database.commit()

        self.login("student", "Student123!")
        response = self.client.post("/checkin/1", data={
            "csrf_token": self.csrf(), "mood": "confused", "note": "刚刚提交的学生反馈",
        })
        self.assertEqual(response.status_code, 302)
        self.clear_session()
        self.login("teacher", "Teacher123!")
        recent = self.client.get("/teacher/sessions/1/summary").json["recent"]
        self.assertEqual(recent[0]["note"], "刚刚提交的学生反馈")
        self.assertGreaterEqual(datetime.fromisoformat(recent[0]["created_at"]), before_submit)
        self.assertEqual(recent[1]["participant"], "AI 采样")

    def test_classroom_trend_and_advice_follow_recent_feedback(self):
        self.login("teacher", "Teacher123!")
        url = "/teacher/sessions/1/summary"
        self.assertEqual(self.client.get(url).json["advice"]["state"], "waiting")
        now = datetime.now().replace(microsecond=0)
        with self.app.app_context():
            database = get_db()
            for mood in ("happy", "calm", "happy"):
                create_ai_checkin(1, mood, 0.9, "live-webcam", (now - timedelta(seconds=10)).isoformat(" "))
            create_ai_checkin(1, "tired", 0.9, "live-webcam", (now - timedelta(minutes=2)).isoformat(" "))
            database.commit()
        summary = self.client.get(url).json
        self.assertEqual(summary["advice"]["state"], "steady")
        self.assertEqual(summary["advice"]["total"], 3)
        self.assertEqual(sum(summary["timeline"]["series"]["tired"]), 1)

        with self.app.app_context():
            database = get_db()
            for mood in ("confused", "confused", "distracted", "anxious"):
                create_ai_checkin(1, mood, 0.9, "live-webcam", now.isoformat(" "))
            database.commit()
        summary = self.client.get(url).json
        self.assertEqual(summary["advice"]["state"], "slow")
        self.assertEqual(summary["advice"]["attention"], 4)
        self.assertIn("简短例子", summary["advice"]["detail"])

        self.clear_session()
        self.login("student", "Student123!")
        page = self.client.get("/history").get_data(as_text=True)
        journey = json.loads(re.search(r'id="student-trend-data">(.*?)</script>', page).group(1))
        self.assertEqual([record["mood"] for record in journey["records"]], ["calm", "confused", "happy"])

    def test_anonymous_checkins_keep_distinct_participant_count(self):
        with self.app.app_context():
            database = get_db()
            database.execute(
                """INSERT INTO users (username, display_name, password_hash, role)
                   VALUES (?, ?, ?, 'student')""",
                ("anonymous2", "第二位学生", generate_password_hash("Student234!")),
            )
            second_student = database.execute("SELECT last_insert_rowid()").fetchone()[0]
            database.execute(
                """INSERT INTO checkins (session_id, user_id, mood, note, is_anonymous, created_at)
                   VALUES (1, ?, 'calm', '', 1, ?)""",
                (second_student, datetime.now().replace(microsecond=0).isoformat(" ")),
            )
            database.commit()
        self.login("teacher", "Teacher123!")
        detail = self.client.get("/teacher/sessions/1")
        self.assertIn(b'data-participants>2</strong>', detail.data)
        summary = self.client.get("/teacher/sessions/1/summary")
        self.assertEqual(summary.json["participants"], 2)

    def test_admin_rejects_invalid_date_ranges(self):
        self.login("admin", "Admin123!")
        self.assertEqual(self.client.get("/admin/records?start=not-a-date").status_code, 400)
        self.assertEqual(
            self.client.get("/admin/records/export?start=2026-10-25&end=2026-10-24").status_code,
            400,
        )

    def test_admin_rejects_invalid_participant_ids_without_changing_list(self):
        self.login("admin", "Admin123!")
        with self.app.app_context():
            before = [
                row["user_id"] for row in get_db().execute(
                    "SELECT user_id FROM session_participants WHERE session_id = 1 ORDER BY user_id"
                ).fetchall()
            ]
        response = self.client.post("/admin/sessions/1/participants", data={
            "user_ids": ["999999"], "csrf_token": self.csrf(),
        })
        self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            after = [
                row["user_id"] for row in get_db().execute(
                    "SELECT user_id FROM session_participants WHERE session_id = 1 ORDER BY user_id"
                ).fetchall()
            ]
        self.assertEqual(after, before)

    def test_recent_24_hour_trend_uses_continuous_local_window(self):
        now = datetime.now().replace(microsecond=0)
        with self.app.app_context():
            database = get_db()
            student_id = database.execute("SELECT id FROM users WHERE username = 'student'").fetchone()[0]
            database.executemany(
                """INSERT INTO checkins (session_id, user_id, mood, note, is_anonymous, created_at)
                   VALUES (1, ?, ?, '', 0, ?)""",
                [
                    (student_id, "happy", (now - timedelta(hours=23)).isoformat(" ")),
                    (student_id, "calm", (now - timedelta(hours=25)).isoformat(" ")),
                ],
            )
            database.commit()
        self.login("admin", "Admin123!")
        response = self.client.get("/admin/")
        match = re.search(rb'id="chart-data">(.+?)</script>', response.data)
        self.assertIsNotNone(match)
        chart_data = json.loads(match.group(1))
        self.assertEqual(len(chart_data["trendLabels"]), 12)
        self.assertEqual(sum(chart_data["trend"]["happy"]), 2)
        self.assertEqual(sum(chart_data["trend"]["calm"]), 1)

    def test_registration_password_change_and_disabled_login(self):
        response = self.client.post("/register", data={
            "username": "newstudent", "display_name": "新同学", "password": "Start123!",
            "role": "student", "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn("注册成功".encode(), response.data)
        self.login("newstudent", "Start123!")
        response = self.client.post("/settings", data={
            "current_password": "Start123!", "new_password": "Changed456!",
            "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn("密码已更新".encode(), response.data)
        self.clear_session()
        self.login("newstudent", "Changed456!")
        self.clear_session()
        with self.app.app_context():
            database = get_db()
            database.execute("UPDATE users SET is_active = 0 WHERE username = 'newstudent'")
            database.commit()
        response = self.client.post("/login", data={
            "username": "newstudent", "password": "Changed456!", "csrf_token": self.csrf(),
        }, follow_redirects=True)
        self.assertIn("用户名或密码不正确".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
