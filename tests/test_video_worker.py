import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import URLError
from werkzeug.serving import make_server

from emotion_checker import create_app
from emotion_checker.db import get_db

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("video_worker", ROOT / "scripts" / "judge_video_emotion_worker.py")
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class VideoWorkerTestCase(unittest.TestCase):
    def test_load_env_accepts_export_syntax_without_logging_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "judge.env.example"
            config.write_text(
                'export JUDGE_BASE_URL="https://example.test"\n'
                'export JUDGE_API_KEY="not-for-logs"\n', encoding="utf-8"
            )
            loaded = worker.load_env(config)
        self.assertEqual(loaded["JUDGE_BASE_URL"], "https://example.test")
        self.assertEqual(loaded["JUDGE_API_KEY"], "not-for-logs")

    def test_request_json_retries_temporary_network_error(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"ok":true}'

        with patch.object(worker.urllib.request, "urlopen", side_effect=[URLError("temporary"), Response()]), \
             patch.object(worker.time, "sleep"):
            result = worker.request_json("https://example.test", {}, {}, attempts=2)
        self.assertEqual(result, {"ok": True})

    def test_result_parser_normalizes_unknown_labels_and_bounds_confidence(self):
        frame = Path("unused.jpg")
        payload = {"output": [{"content": [{"type": "output_text", "text":
            '{"face_detected":true,"emotion":"surprised","confidence":1.4,"note":"test"}'}]}]}
        with patch.object(worker.base64, "b64encode", return_value=b"frame"), \
             patch.object(Path, "read_bytes", return_value=b"image"), \
             patch.object(worker, "request_json", return_value=payload):
            result = worker.analyze_frame(frame, {"JUDGE_BASE_URL": "https://example.test", "JUDGE_API_KEY": "secret"}, "test")
        self.assertEqual(result["emotion"], "unknown")
        self.assertEqual(result["confidence"], 1.0)
        self.assertTrue(result["face_detected"])

    def test_post_results_uses_separate_backend_token_and_session(self):
        with patch.object(worker, "request_json", return_value={"accepted": [1]}) as request:
            response = worker.post_results("http://localhost:5000", "backend-secret", 7, [{"mood": "happy"}])
        self.assertEqual(response, {"accepted": [1]})
        args, kwargs = request.call_args
        self.assertEqual(args[0], "http://localhost:5000/api/ai/emoji-results")
        self.assertEqual(args[1]["X-AI-Service-Token"], "backend-secret")
        self.assertEqual(args[2]["session_id"], 7)
        self.assertNotIn("backend-secret", json.dumps(args[2]))

    def test_video_frames_flow_through_vision_api_into_isolated_database(self):
        ffmpeg = next((path for path in worker.FFMPEG_CANDIDATES if path and path.exists()), None)
        video = ROOT / "docs" / "demo-videos" / "AI案例3-平静困惑开心-10秒.mp4"
        if ffmpeg is None or not video.exists():
            self.skipTest("demo video or ffmpeg unavailable")

        predictions = iter([
            {"face_detected": True, "emotion": "calm", "confidence": 0.84, "note": "calm"},
            {"face_detected": True, "emotion": "confused", "confidence": 0.82, "note": "confused"},
            {"face_detected": True, "emotion": "happy", "confidence": 0.96, "note": "happy"},
        ])

        class JudgeHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                result = next(predictions)
                response = json.dumps({"output": [{"content": [{
                    "type": "output_text", "text": json.dumps(result),
                }]}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, *_args):
                pass

        judge = ThreadingHTTPServer(("127.0.0.1", 0), JudgeHandler)
        judge_thread = threading.Thread(target=judge.serve_forever, daemon=True)
        judge_thread.start()
        backend_token = "integration-test-token"
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite3"
            config = Path(directory) / "judge.env"
            config.write_text(
                f"JUDGE_BASE_URL=http://127.0.0.1:{judge.server_port}\nJUDGE_API_KEY=fake-key\n",
                encoding="utf-8",
            )
            app = create_app({
                "TESTING": True, "SECRET_KEY": "integration-test", "DATABASE": str(database),
                "AI_SERVICE_TOKEN": backend_token, "AI_CONFIDENCE_THRESHOLD": 0.65,
            })
            with app.app_context():
                session_id = get_db().execute(
                    "SELECT id FROM class_sessions WHERE status='open' ORDER BY id LIMIT 1"
                ).fetchone()[0]
            backend = make_server("127.0.0.1", 0, app)
            backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
            backend_thread.start()
            environment = os.environ.copy()
            environment["EMOTION_AI_SERVICE_TOKEN"] = backend_token
            try:
                result = subprocess.run([
                    sys.executable, str(ROOT / "scripts" / "judge_video_emotion_worker.py"), str(video),
                    "--env", str(config), "--model", "test-vision", "--interval", "3.3",
                    "--threshold", "0.65", "--max-frames", "3", "--session-id", str(session_id),
                    "--backend", f"http://127.0.0.1:{backend.server_port}",
                ], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn('"accepted"', result.stdout)
                connection = sqlite3.connect(database)
                try:
                    rows = connection.execute(
                        "SELECT mood, source, confidence, created_at FROM checkins WHERE source='AI' ORDER BY id"
                    ).fetchall()
                finally:
                    connection.close()
                self.assertEqual([row[0] for row in rows], ["calm", "confused", "happy"])
                self.assertTrue(all(row[1] == "AI" and row[2] >= 0.65 and row[3] for row in rows))
            finally:
                backend.shutdown()
                backend.server_close()
                backend_thread.join(timeout=2)
                judge.shutdown()
                judge.server_close()
                judge_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
