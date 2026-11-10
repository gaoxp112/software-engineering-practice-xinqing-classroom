import os
from dataclasses import dataclass, field
from datetime import datetime
from threading import Event, Lock, Thread
from time import monotonic

from .db import get_db
from .repository import create_ai_checkin, session as find_session
from .moods import MOODS


SAMPLE_INTERVAL = 3.0
PREVIEW_INTERVAL = 0.1
CONFIDENCE_THRESHOLD = 0.65
ACTIVE_STATES = {"starting", "running", "stopping"}
STATE_MESSAGES = {
    "idle": "摄像头待启动",
    "starting": "正在打开摄像头…",
    "running": "正在实时识别",
    "stopping": "正在停止摄像头…",
    "stopped": "摄像头已停止",
}


def open_camera():
    import cv2

    if os.name == "nt":
        capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if capture.isOpened():
            return capture
        capture.release()
    return cv2.VideoCapture(0)


@dataclass
class CameraRun:
    session_id: int
    stop_requested: Event = field(default_factory=Event)
    state: str = "starting"
    latest: dict | None = None
    preview: tuple[bytes, dict] | None = None
    saved_count: int = 0
    error: str = ""


class CameraWorker:
    def __init__(self, app):
        self.app = app
        self.lock = Lock()
        self.run = None

    def start(self, session_id):
        with self.lock:
            if self.run and self.run.state in ACTIVE_STATES:
                return self.run.session_id == session_id
            self.run = CameraRun(session_id)
            Thread(target=self._capture, args=(self.run,), daemon=True).start()
            return True

    def stop(self, session_id):
        with self.lock:
            if self.run and self.run.session_id == session_id and self.run.state in ACTIVE_STATES:
                self.run.stop_requested.set()
                self.run.state = "stopping"

    def status(self, session_id):
        with self.lock:
            run = self.run if self.run and self.run.session_id == session_id else None
            state = run.state if run else "idle"
            return {
                "state": state,
                "message": STATE_MESSAGES.get(state) or run.error,
                "latest": run.latest if run else None,
                "saved_count": run.saved_count if run else 0,
            }

    def preview(self, session_id):
        with self.lock:
            run = self.run
            if run and run.session_id == session_id and run.state == "running":
                return run.preview
            return None

    def _capture(self, run):
        capture = None
        error = ""
        try:
            import cv2
            from scripts.local_expression import LocalExpressionModel

            model = LocalExpressionModel()
            if run.stop_requested.is_set():
                return
            capture = open_camera()
            if not capture.isOpened():
                error = "无法打开摄像头，请检查 Windows 摄像头权限或关闭正在使用摄像头的程序。"
                return
            with self.lock:
                if run.stop_requested.is_set():
                    return
                run.state = "running"

            next_sample = 0.0
            next_preview = 0.0
            failed_reads = 0
            while not run.stop_requested.is_set():
                ok, image = capture.read()
                if not ok:
                    failed_reads += 1
                    if failed_reads >= 5:
                        error = "摄像头读取中断，请重新启动识别。"
                        break
                    run.stop_requested.wait(0.2)
                    continue
                failed_reads = 0
                now = monotonic()
                if now < next_preview:
                    continue
                next_preview = now + PREVIEW_INTERVAL
                prediction = model.analyze_image(image)
                if now >= next_sample:
                    next_sample = now + SAMPLE_INTERVAL
                    if not self._record_sample(run, prediction):
                        break
                encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if encoded:
                    with self.lock:
                        run.preview = (jpeg.tobytes(), prediction)
        except Exception:
            self.app.logger.exception("Classroom camera recognition failed")
            error = "识别中断，请重新启动摄像头。"
        finally:
            if capture is not None:
                capture.release()
            with self.lock:
                run.preview = None
                run.error = error if not run.stop_requested.is_set() else ""
                run.state = "error" if run.error else "stopped"

    def _record_sample(self, run, prediction):
        mood = prediction.get("mood")
        confidence = prediction["confidence"]
        timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
        with self.lock, self.app.app_context():
            if run.stop_requested.is_set():
                return False
            database = get_db()
            session = find_session(run.session_id)
            if session is None or session["phase"] != "open":
                return False
            saved = False
            if mood and confidence >= CONFIDENCE_THRESHOLD:
                record_id = create_ai_checkin(run.session_id, mood, confidence, "live-webcam", timestamp)
                if record_id is None:
                    return False
                database.commit()
                run.saved_count += 1
                saved = True
            run.latest = {
                "mood": MOODS[mood] if mood else None,
                "confidence": confidence,
                "saved": saved,
                "time": timestamp[11:19],
            }
        return True
