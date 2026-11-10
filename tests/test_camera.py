import json
import tempfile
import unittest
from itertools import chain, repeat
from pathlib import Path
from time import monotonic, sleep
from unittest.mock import Mock, patch

import numpy as np

from emotion_checker import create_app
from emotion_checker.db import get_db


class CameraTestCase(unittest.TestCase):
    def test_teacher_camera_records_anonymous_samples_and_stops_when_class_ends(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app({"TESTING": True, "DATABASE": str(Path(directory) / "test.sqlite3")})
            client = app.test_client()
            url = "/teacher/sessions/1/camera"
            preview_url = f"{url}/preview"
            self.assertEqual(client.post("/api/auth/login", json={
                "username": "teacher", "password": "Teacher123!",
            }).status_code, 200)
            page = client.get("/teacher/sessions/1")
            self.assertIn("开始识别", page.get_data(as_text=True))
            self.assertIn("data-camera-preview-url", page.get_data(as_text=True))
            self.assertEqual(client.get(preview_url).status_code, 204)
            self.assertEqual(client.get(preview_url, environ_overrides={"REMOTE_ADDR": "192.0.2.10"}).status_code, 403)
            with client.session_transaction() as session:
                csrf = session["csrf_token"]

            capture = Mock()
            capture.isOpened.return_value = True
            frame = np.zeros((120, 160, 3), dtype=np.uint8)
            box = [20, 30, 60, 70]

            def read_frame():
                sleep(0.01)
                return True, frame

            capture.read.side_effect = read_frame
            model = Mock()
            model.analyze_image.side_effect = chain(
                [{"mood": "happy", "confidence": 0.4, "box": box}],
                repeat({"mood": "calm", "confidence": 0.9, "box": box}),
            )

            def wait_until(predicate):
                deadline = monotonic() + 3
                while monotonic() < deadline:
                    result = client.get(url).json
                    if predicate(result):
                        return result
                    sleep(0.02)
                self.fail(f"Camera state did not update: {result}")

            with patch("emotion_checker.camera.open_camera", return_value=capture), patch(
                "scripts.local_expression.LocalExpressionModel", return_value=model,
            ), patch("emotion_checker.camera.SAMPLE_INTERVAL", 0.25):
                try:
                    self.assertEqual(client.post(url, data={"action": "start"}).status_code, 400)
                    self.assertEqual(client.post(url, data={"action": "start", "csrf_token": csrf}).status_code, 302)
                    result = wait_until(lambda state: state["saved_count"] == 1)
                    self.assertEqual(result["latest"]["mood"]["label"], "平静")
                    preview = client.get(preview_url)
                    self.assertEqual(preview.mimetype, "image/jpeg")
                    self.assertTrue(preview.data.startswith(b"\xff\xd8"))
                    self.assertEqual(json.loads(preview.headers["X-Camera-Detection"])["box"], box)
                    self.assertEqual(client.post("/teacher/sessions/1/toggle", data={"csrf_token": csrf}).status_code, 302)
                    self.assertFalse(wait_until(lambda state: state["state"] == "stopped")["is_open"])
                    self.assertEqual(client.get(preview_url).status_code, 204)
                    capture.release.assert_called_once()
                    with app.app_context():
                        rows = get_db().execute("SELECT mood, user_id, is_anonymous, device_id FROM checkins WHERE source='AI'").fetchall()
                        self.assertEqual([tuple(row) for row in rows], [("calm", None, 1, "live-webcam")])
                finally:
                    app.extensions["camera"].stop(1)
                    wait_until(lambda state: state["state"] in {"idle", "stopped", "error"})
