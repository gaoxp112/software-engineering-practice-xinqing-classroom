import os
import tempfile
import unittest

from emotion_checker import create_app
from emotion_checker.db import get_db


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        handle.close()
        self.db_file = handle.name
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "api-test",
            "DATABASE": self.db_file,
            "AI_SERVICE_TOKEN": "test-ai-token",
            "AI_CONFIDENCE_THRESHOLD": 0.75,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.db_file)

    def api_login(self, username, password):
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)

    def test_openapi_and_unauthenticated_error_shape(self):
        response = self.client.get("/api/users/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["ok"], False)
        self.assertEqual(response.json["error"]["code"], "AUTH_REQUIRED")
        self.assertEqual(self.client.get("/api/openapi.json").status_code, 200)

    def test_student_api_flow(self):
        response = self.client.post("/api/auth/register", json={
            "username": "api_student", "display_name": "API Student",
            "email": "api@example.test", "password": "ApiStudent123!", "role": "student",
        })
        self.assertEqual(response.status_code, 201)
        self.api_login("api_student", "ApiStudent123!")
        self.assertEqual(self.client.get("/api/users/me").json["data"]["user"]["email"], "api@example.test")
        response = self.client.post("/api/emoji", json={"session_id": 1, "mood": "happy", "note": "api"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get("/api/emoji/history").json["data"]["records"][0]["source"], "MANUAL")
        self.assertEqual(self.client.get("/api/emoji/statistics").json["data"]["total"], 1)
        self.assertEqual(self.client.get("/api/emoji/statistics?session_id=1").status_code, 403)

    def test_teacher_session_statistics_are_scoped(self):
        self.api_login("teacher", "Teacher123!")
        self.assertEqual(self.client.get("/api/emoji/statistics?session_id=1").status_code, 200)
        self.client.post("/api/auth/login", json={"username": "student", "password": "Student123!"})
        self.assertEqual(self.client.get("/api/emoji/statistics?session_id=9999").status_code, 404)

    def test_admin_schedule_statistics_and_realtime(self):
        self.api_login("admin", "Admin123!")
        response = self.client.get("/api/admin/users")
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            student_id = get_db().execute("SELECT id FROM users WHERE username='student'").fetchone()[0]
        response = self.client.post("/api/admin/sessions/1/schedule", json={"user_ids": [student_id]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/dashboard/realtime?sessionId=1").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/statistics?from=invalid").status_code, 400)

    def test_ai_ingest_requires_token_and_filters_confidence(self):
        payload = {"session_id": 1, "results": [
            {"mood": "happy", "confidence": 0.9},
            {"mood": "calm", "confidence": 0.4},
        ]}
        self.assertEqual(self.client.post("/api/ai/emoji-results", json=payload).status_code, 401)
        response = self.client.post("/api/ai/emoji-results", json=payload, headers={"X-AI-Service-Token": "test-ai-token"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json["data"]["accepted"]), 1)
        self.assertEqual(len(response.json["data"]["rejected"]), 1)
        with self.app.app_context():
            row = get_db().execute("SELECT source, user_id, confidence FROM checkins WHERE source='AI'").fetchone()
            self.assertEqual((row["source"], row["user_id"]), ("AI", None))
            self.assertAlmostEqual(row["confidence"], 0.9)
        self.api_login("admin", "Admin123!")
        self.assertEqual(self.client.get("/admin/records?mood=happy").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/emoji/export").status_code, 200)

    def test_ai_ingest_maps_original_expression_labels(self):
        self.api_login("student", "Student123!")
        response = self.client.post("/api/emoji", json={"session_id": 1, "mood": "surprised"})
        self.assertEqual(response.status_code, 400)

        response = self.client.post("/api/ai/emoji-results", json={
            "session_id": 1, "results": [{"mood": "surprised", "confidence": 0.95}],
        }, headers={"X-AI-Service-Token": "test-ai-token"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json["data"]["accepted"]), 1)
        with self.app.app_context():
            mood = get_db().execute("SELECT mood FROM checkins WHERE source = 'AI'").fetchone()[0]
            self.assertEqual(mood, "confused")

        self.api_login("admin", "Admin123!")
        page = self.client.get("/admin/records?mood=confused")
        self.assertIn("困惑", page.get_data(as_text=True))
        self.assertNotIn("惊讶", page.get_data(as_text=True))
        self.assertIn("95%", page.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
