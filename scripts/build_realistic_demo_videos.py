from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "demo-videos" / "generated"
FRAMES = ROOT / "docs" / "demo-videos" / "realistic-frames"
WIDTH, HEIGHT = 1280, 720
FPS, SECONDS = 24, 10


def font(size, bold=False):
    names = ["msyhbd.ttc", "msyh.ttc"] if bold else ["msyh.ttc", "simhei.ttf"]
    for name in names:
        path = Path(r"C:\Windows\Fonts") / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


TITLE = font(30, True)
LABEL = font(25, True)
BODY = font(20)
SMALL = font(16)


def cover_crop(image, width, height, zoom=1.0, x_bias=0.5, y_bias=0.48):
    scale = max(width / image.width, height / image.height) * zoom
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    left = int((resized.width - width) * x_bias)
    top = int((resized.height - height) * y_bias)
    return resized.crop((left, top, left + width, top + height))


def frame_image(source, progress, label, confidence, color, note):
    zoom = 1.0 + progress * 0.035
    base = cover_crop(source, WIDTH, HEIGHT, zoom=zoom)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, 0, WIDTH, 76), fill=(16, 52, 47, 220))
    draw.text((38, 20), "心晴课堂 · AI 视频情绪分析案例", font=TITLE, fill="white")
    draw.rounded_rectangle((785, 535, 1240, 685), radius=20, fill=(255, 255, 255, 232))
    draw.text((815, 555), f"识别：{label}", font=LABEL, fill=color)
    draw.text((815, 597), f"置信度：{confidence:.2f}", font=BODY, fill="#243E3A")
    draw.text((815, 630), note, font=SMALL, fill="#536E69")
    draw.rounded_rectangle((40, 650, 740, 674), radius=12, fill=(228, 237, 234, 215))
    draw.rounded_rectangle((40, 650, 40 + int(700 * progress), 674), radius=12, fill=color)
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def build(name, scenes):
    target = FRAMES / name
    target.mkdir(parents=True, exist_ok=True)
    sources = {key: Image.open(ASSETS / f"{key}.png").convert("RGB") for key, *_ in scenes}
    for index in range(FPS * SECONDS):
        global_progress = index / (FPS * SECONDS - 1)
        scene_index = min(int(global_progress * len(scenes)), len(scenes) - 1)
        key, label, confidence, color, note = scenes[scene_index]
        local_progress = (global_progress * len(scenes)) % 1
        frame = frame_image(sources[key], global_progress, label, confidence, color, note)
        if 0.46 < local_progress < 0.54 and scene_index < len(scenes) - 1:
            amount = abs(local_progress - 0.5) / 0.04
            frame = Image.blend(Image.new("RGB", frame.size, "white"), frame, min(amount, 1))
        frame.save(target / f"frame-{index:04d}.jpg", quality=90)


def main():
    build("case-01-positive", [
        ("calm", "平静", 0.88, "#16806F", "课堂开始阶段"),
        ("happy", "开心", 0.93, "#16806F", "理解知识点后"),
    ])
    build("case-02-attention", [
        ("confused", "困惑", 0.86, "#E7674A", "遇到理解障碍"),
        ("anxious", "焦虑", 0.90, "#E7674A", "需要教师关注"),
    ])
    build("case-03-mixed", [
        ("calm", "平静", 0.84, "#16806F", "正常听课"),
        ("confused", "困惑", 0.82, "#E5A326", "知识点切换"),
        ("happy", "开心", 0.91, "#16806F", "教师解释后"),
    ])


if __name__ == "__main__":
    main()
