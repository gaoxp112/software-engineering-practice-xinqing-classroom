"""Lightweight video emotion worker for the experiment.

Extracts frames with FFmpeg and uses a local model or a configured Judge API.
Only the classification results are sent to the classroom ingestion endpoint.
"""

import argparse
import base64
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT.parent / "judge.env.example"
FFMPEG_CANDIDATES = [
    Path(os.environ.get("FFMPEG_EXE", "")) if os.environ.get("FFMPEG_EXE") else None,
    *Path(r"C:\Program Files\Tencent\QQBrowser").glob("*/ffmpeg/ffmpeg.exe"),
]
ALLOWED = {"calm", "happy", "confused", "anxious", "tired", "distracted", "unknown"}


def load_env(path):
    values = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    required = ["JUDGE_BASE_URL", "JUDGE_API_KEY"]
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("Missing config: " + ", ".join(missing))
    return values


def find_ffmpeg():
    from_path = shutil.which("ffmpeg")
    if from_path:
        return Path(from_path)
    for path in FFMPEG_CANDIDATES:
        if path is not None and path.exists():
            return path
    raise RuntimeError("ffmpeg was not found; install ffmpeg or set FFMPEG_EXE to ffmpeg.exe")


def request_json(url, headers, body, timeout=120, attempts=3):
    encoded = json.dumps(body).encode("utf-8")
    for attempt in range(attempts):
        request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code not in (408, 425, 429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise RuntimeError(f"Network request failed: {exc}") from exc
        time.sleep(min(2 ** attempt + random.random(), 8))
    raise RuntimeError("Request failed after retries")


def extract_frames(video, interval, workdir, max_frames):
    pattern = Path(workdir) / "frame-%04d.jpg"
    command = [
        str(find_ffmpeg()), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-vf", f"fps=1/{interval},scale=960:-2", "-frames:v", str(max_frames),
        "-q:v", "3", str(pattern),
    ]
    subprocess.run(command, check=True)
    return sorted(Path(workdir).glob("frame-*.jpg"))


def analyze_frame(frame, config, model):
    encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
    prompt = (
        "Analyze only the visible facial expression in this classroom video frame. "
        "Do not identify the person. Return JSON only with keys face_detected, emotion, confidence, note. "
        "emotion must be calm, happy, confused, anxious, tired, distracted, or unknown. "
        "confidence must be a number from 0 to 1."
    )
    body = {
        "model": model, "store": False, "max_output_tokens": 100,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": "data:image/jpeg;base64," + encoded},
            ],
        }],
    }
    response = request_json(
        config["JUDGE_BASE_URL"].rstrip("/") + "/v1/responses",
        {"Authorization": "Bearer " + config["JUDGE_API_KEY"], "Content-Type": "application/json"},
        body, attempts=1,
    )
    text = ""
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text += content.get("text", "")
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    result = json.loads(text)
    emotion = str(result.get("emotion", "unknown")).lower()
    result["emotion"] = emotion if emotion in ALLOWED else "unknown"
    result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0))))
    result["face_detected"] = bool(result.get("face_detected"))
    return result


def post_results(endpoint, token, session_id, results):
    body = {"session_id": session_id, "results": results}
    return request_json(
        endpoint.rstrip("/") + "/api/ai/emoji-results",
        {"X-AI-Service-Token": token, "Content-Type": "application/json"}, body,
        timeout=30, attempts=1,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--local", action="store_true", help="run bundled OpenCV models on the CPU")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--interval", type=float, default=2.5, help="seconds between sampled frames")
    parser.add_argument("--threshold", type=float, default=0.65)
    parser.add_argument("--max-frames", type=int, default=60)
    parser.add_argument("--session-id", type=int)
    parser.add_argument("--backend", default="http://127.0.0.1:5000")
    parser.add_argument("--device-id", default="demo-video")
    args = parser.parse_args()
    if not args.video.is_file():
        parser.error("video file does not exist")
    if args.interval <= 0 or not 0 <= args.threshold <= 1 or not 1 <= args.max_frames <= 500:
        parser.error("interval, threshold, or max-frames is outside the supported range")
    if args.local:
        if not __package__:
            sys.path.insert(0, str(ROOT))
        from scripts.local_expression import LocalExpressionModel

        predict = LocalExpressionModel().analyze_frame
    else:
        config = load_env(args.env)

        def predict(frame):
            return analyze_frame(frame, config, args.model)

    started_at = datetime.now().replace(microsecond=0)
    with tempfile.TemporaryDirectory(prefix="emotion-worker-") as directory:
        frames = extract_frames(args.video, args.interval, directory, args.max_frames)
        accepted = []
        if not frames:
            raise RuntimeError("No frames could be extracted from this video")
        for index, frame in enumerate(frames):
            result = predict(frame)
            sample_time = started_at + timedelta(seconds=index * args.interval)
            print(json.dumps({"frame": index, "sampled_at": sample_time.isoformat(sep=" "), **result}, ensure_ascii=False))
            if result.get("face_detected") and result["emotion"] != "unknown" and result["confidence"] >= args.threshold:
                accepted.append({
                    "mood": result.get("mood", result["emotion"]), "confidence": result["confidence"],
                    "device_id": args.device_id, "timestamp": sample_time.isoformat(sep=" "),
                })
    token = os.environ.get("EMOTION_AI_SERVICE_TOKEN", "")
    if args.session_id and token and accepted:
        response = post_results(args.backend, token, args.session_id, accepted)
        print(json.dumps({"backend": response}, ensure_ascii=False))
    elif not accepted:
        print(json.dumps({"accepted": [], "reason": "no predictions met the threshold"}))
    else:
        print(json.dumps({"dry_run": True, "accepted": accepted, "reason": "missing session id or backend token"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
