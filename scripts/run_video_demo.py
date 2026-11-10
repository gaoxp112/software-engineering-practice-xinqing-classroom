"""One-command local demo: choose an open class and video, then ingest AI results."""

import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from judge_video_emotion_worker import load_env


ROOT = Path(__file__).resolve().parents[1]


def database_path():
    configured = os.environ.get("EMOTION_DATABASE")
    return Path(configured) if configured else ROOT / "instance" / "emotion_checker.sqlite3"


def open_sessions():
    path = database_path()
    if not path.exists():
        raise RuntimeError("应用数据库不存在，请先从项目目录启动一次系统。")
    sys.path.insert(0, str(ROOT))
    from emotion_checker import create_app, services

    app = create_app({"DATABASE": str(path)})
    with app.app_context():
        return services.open_classrooms()


def choose_video(initial_dir):
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            title="选择课堂情绪分析短视频",
            initialdir=str(initial_dir),
            filetypes=[("Video files", "*.mp4 *.mov *.m4v *.avi *.mkv *.webm"), ("All files", "*.*")],
        )
        root.destroy()
        if selected:
            return Path(selected)
    except Exception:
        pass
    while True:
        selected = input("输入视频文件完整路径：").strip().strip("\"")
        path = Path(selected)
        if path.is_file():
            return path
        print("找不到该视频文件，请重试。")


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_until_ready(process, url):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("本地 Web 服务启动失败，请确认项目依赖已安装。")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    process.terminate()
    raise RuntimeError("等待本地 Web 服务超时。")


def main():
    parser = argparse.ArgumentParser(description="选择一段视频并把 AI 结果写入本地课堂系统")
    parser.add_argument("--video", type=Path, help="视频路径；不传则弹出文件选择框")
    parser.add_argument("--session-id", type=int, help="课堂 ID；不传则从开放课堂列表选择")
    parser.add_argument("--choose-session", action="store_true", help="手动选择课堂，而不是默认最新开放课堂")
    parser.add_argument("--env", type=Path, help="改用 Judge API，并读取指定配置文件")
    parser.add_argument("--interval", type=float, default=3.3, help="每隔多少秒抽取一帧")
    parser.add_argument("--threshold", type=float, default=0.65)
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if args.interval <= 0 or not 0 <= args.threshold <= 1:
        parser.error("抽帧间隔必须大于 0，置信度阈值必须在 0 到 1 之间。")
    if args.env:
        load_env(args.env)
    rows = open_sessions()
    if not rows:
        raise RuntimeError("没有开放课堂，请先用教师账号创建或重新开放一个课堂。")
    if args.session_id:
        selected = next((row for row in rows if row["id"] == args.session_id), None)
        if selected is None:
            raise RuntimeError("指定课堂不存在或已关闭。")
    else:
        selected = rows[0]
        if args.choose_session:
            for row in rows:
                print(f"{row['id']}: {row['course_name']} / {row['class_name']} / {row['title']}")
            choice = input(f"课堂 ID（默认 {selected['id']}）：").strip()
            if choice:
                selected = next((row for row in rows if row["id"] == int(choice)), None)
                if selected is None:
                    raise RuntimeError("指定课堂不存在或已关闭。")
    video = args.video if args.video else choose_video(ROOT / "docs" / "demo-videos")
    if not video.is_file():
        raise RuntimeError("视频文件不存在。")

    port = free_port()
    endpoint = f"http://127.0.0.1:{port}"
    backend_token = secrets.token_urlsafe(36)
    server_env = os.environ.copy()
    server_env["EMOTION_AI_SERVICE_TOKEN"] = backend_token
    server_env["EMOTION_AI_THRESHOLD"] = str(args.threshold)
    server_env.setdefault("EMOTION_SECRET_KEY", secrets.token_urlsafe(36))
    server = subprocess.Popen(
        [sys.executable, "-m", "waitress", f"--listen=127.0.0.1:{port}", "run:app"],
        cwd=ROOT, env=server_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    print(f"课堂：{selected['course_name']} / {selected['title']}")
    print(f"视频：{video.name}")
    print("正在启动本地服务并进行视频识别……")
    try:
        wait_until_ready(server, endpoint + "/health")

        worker_env = os.environ.copy()
        worker_env["EMOTION_AI_SERVICE_TOKEN"] = backend_token
        command = [
            sys.executable, str(ROOT / "scripts" / "judge_video_emotion_worker.py"), str(video),
            "--interval", str(args.interval),
            "--threshold", str(args.threshold), "--session-id", str(selected["id"]),
            "--backend", endpoint, "--device-id", "video-demo-api" if args.env else "video-demo-local",
        ]
        command.extend(["--env", str(args.env), "--model", args.model] if args.env else ["--local"])
        result = subprocess.run(command, cwd=ROOT, env=worker_env, check=False)
        if result.returncode:
            raise RuntimeError("视频分析未完成，请根据上方错误排查。")

        records_url = endpoint + "/admin/records"
        print("视频分析结束。通过阈值的结果已提交到课堂数据库。")
        print("请在浏览器管理员登录页核验 AI 来源与置信度：" + records_url)
        print("管理员演示账号见 README。完成核验和录制后，回到本窗口按 Enter 关闭临时服务。")
        if not args.no_browser:
            webbrowser.open(records_url)
        input()
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("错误：" + str(exc), file=sys.stderr)
        raise SystemExit(1)
