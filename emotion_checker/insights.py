from datetime import datetime, timedelta

from . import repository as repo
from .moods import MOODS


TREND_MINUTES = 15
MIN_ADVICE_RECORDS = 3
TEACHING_ACTIONS = {
    "confused": "用一个简短例子再讲一遍当前要点。",
    "tired": "留一点时间让学生回顾刚讲的内容。",
    "anxious": "给学生留出思考和提问的时间。",
    "distracted": "加入一道简短的互动题，再进入下一部分。",
}


def classroom_insights(session_id):
    now = datetime.now().replace(microsecond=0)
    recent_from = now - timedelta(minutes=1)
    start = now.replace(second=0) - timedelta(minutes=TREND_MINUTES - 1)
    latest = repo.latest_checkin_time(session_id, now.isoformat(" "))
    end = datetime.fromisoformat(latest) if latest and latest < start.isoformat(" ") else now
    start = end.replace(second=0) - timedelta(minutes=TREND_MINUTES - 1)
    rows = repo.timed_moods(start.isoformat(" "), end.isoformat(" "), session_id)

    series = {mood: [0] * TREND_MINUTES for mood in MOODS}
    recent_counts = dict.fromkeys(MOODS, 0)
    for row in rows:
        moment = datetime.fromisoformat(row["created_at"])
        minute = int((moment - start).total_seconds() // 60)
        series[row["mood"]][minute] += 1
        if moment >= recent_from:
            recent_counts[row["mood"]] += 1

    total = sum(recent_counts.values())
    positive = recent_counts["happy"] + recent_counts["calm"]
    if total < MIN_ADVICE_RECORDS:
        state, title = "waiting", "正在收集课堂反馈"
        detail = f"最近 1 分钟达到 {MIN_ADVICE_RECORDS} 条反馈后，生成教学建议。"
    elif positive * 2 > total:
        state, title = "steady", "继续保持当前讲解节奏"
        detail = "最近 1 分钟开心和平静占多数，可以延续当前的讲解方式。"
    else:
        state, title = "slow", "建议放慢讲解节奏"
        focus = max(TEACHING_ACTIONS, key=recent_counts.get)
        detail = f"近 1 分钟有 {recent_counts[focus]} 条{MOODS[focus]['label']}反馈。{TEACHING_ACTIONS[focus]}"

    return {
        "timeline": {
            "labels": [(start + timedelta(minutes=i)).strftime("%H:%M") for i in range(TREND_MINUTES)],
            "series": series,
            "range": f"{start:%m-%d %H:%M} 至 {end:%m-%d %H:%M}",
            "total": len(rows),
        },
        "advice": {"state": state, "title": title, "detail": detail,
                   "total": total, "positive": positive, "attention": total - positive},
    }
