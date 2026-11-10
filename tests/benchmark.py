import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from emotion_checker import create_app
from emotion_checker.db import get_db


def timed(client, path, runs=20):
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        response = client.get(path)
        assert response.status_code == 200
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return {"median_ms": round(statistics.median(samples), 2), "p95_ms": round(samples[int(runs * .95) - 1], 2)}


def main():
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    handle.close()
    try:
        app = create_app({"TESTING": True, "SECRET_KEY": "benchmark", "DATABASE": handle.name})
        with app.app_context():
            database = get_db()
            student_id = database.execute("SELECT id FROM users WHERE username = 'student'").fetchone()[0]
            now = datetime.now().replace(microsecond=0)
            moods = ("happy", "calm", "confused", "tired", "anxious", "distracted")
            rows = [
                (1, student_id, moods[index % len(moods)], f"基准记录 {index}", index % 7 == 0,
                 (now - timedelta(seconds=index * 5)).isoformat(" "))
                for index in range(10000)
            ]
            database.executemany(
                """INSERT INTO checkins (session_id, user_id, mood, note, is_anonymous, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""", rows,
            )
            database.commit()
        client = app.test_client()
        client.get("/login")
        with client.session_transaction() as session:
            token = session["csrf_token"]
        client.post("/login", data={"username": "admin", "password": "Admin123!", "csrf_token": token})
        results = {
            "record_count": 10003,
            "admin_overview": timed(client, "/admin/"),
            "records_page": timed(client, "/admin/records"),
            "csv_export": timed(client, "/admin/records/export", runs=5),
        }
        print(results)
    finally:
        os.unlink(handle.name)


if __name__ == "__main__":
    main()
