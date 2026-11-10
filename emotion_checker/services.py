"""Business rules and transactions shared by the HTML and REST controllers."""

import csv
import io
import json
import math
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from . import repository as repo
from .db import get_db, write_transaction
from .insights import classroom_insights
from .moods import EXPRESSION_TO_MOOD, MOODS
from .security import safe_csv_value


class ServiceError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def audit(action, user_id=None, details=None):
    repo.audit(action, user_id, json.dumps(details or {}, ensure_ascii=False))


def active_user(user_id):
    return repo.user(user_id, active_only=True)


def authenticate(username, password, *, log=False):
    user = repo.user_by_name(username)
    if user is None or not user["is_active"] or not check_password_hash(user["password_hash"], password):
        raise ServiceError("INVALID_CREDENTIALS", "用户名或密码不正确。", 401)
    if log:
        with get_db():
            audit("auth.login", user["id"])
    return user


def _strong_password(password):
    return len(password) >= 8 and any(c.isalpha() for c in password) and any(c.isdigit() for c in password)


def create_account(username, name, password, role, *, email="", mode="web", admin_invited=False):
    valid_name = (re.fullmatch(r"[A-Za-z0-9_]{3,24}", username) if mode == "web" else
                  3 <= len(username) <= 24 and username.replace("_", "").isalnum())
    if not valid_name:
        raise ServiceError("INVALID_USERNAME", "用户名需为 3-24 位字母、数字或下划线。")
    if not 2 <= len(name) <= 30 or (mode == "admin" and role not in ("student", "teacher", "admin")):
        message = "请填写有效的姓名和角色。" if mode == "admin" else "显示名称需为 2-30 个字符。"
        raise ServiceError("INVALID_DISPLAY_NAME", message)
    if not _strong_password(password):
        raise ServiceError("WEAK_PASSWORD", "密码至少 8 位且同时包含字母和数字。")
    if email and ("@" not in email or len(email) > 120):
        raise ServiceError("INVALID_EMAIL", "邮箱格式无效。")
    if role == "admin" and mode == "api":
        if not admin_invited:
            raise ServiceError("ADMIN_REGISTRATION_DISABLED", "管理员注册需要邀请令牌。", 403)
    elif role not in ("student", "teacher") and (role != "admin" or mode != "admin"):
        raise ServiceError("INVALID_ROLE", "请选择有效的用户角色。")
    try:
        with get_db():
            user_id = repo.create_user(username, name, generate_password_hash(password), role, email)
            if mode == "api":
                audit("auth.register", user_id, {"role": role})
    except sqlite3.IntegrityError as exc:
        if exc.sqlite_errorcode != sqlite3.SQLITE_CONSTRAINT_UNIQUE:
            raise
        raise ServiceError("USERNAME_EXISTS", "该用户名已被使用。", 409) from exc
    return repo.user(user_id)


def change_password(user, current, new, *, log=False):
    if not check_password_hash(user["password_hash"], current):
        raise ServiceError("INVALID_PASSWORD", "当前密码不正确。")
    if not _strong_password(new):
        raise ServiceError("WEAK_PASSWORD", "新密码至少 8 位且同时包含字母和数字。")
    with get_db():
        repo.update_password(user["id"], generate_password_hash(new))
        if log:
            audit("auth.password_changed", user["id"])


def users(keyword, *, search_email=False):
    return repo.users(keyword, search_email=search_email)


def toggle_user(user_id, actor_id):
    if user_id == actor_id:
        raise ServiceError("CURRENT_USER", "不能停用当前管理员账号。")
    with get_db():
        if not repo.toggle_user(user_id):
            raise ServiceError("USER_NOT_FOUND", "用户不存在。", 404)


def require_session(session_id, *, teacher_id=None, must_be_open=False):
    session = repo.session(session_id)
    if session is None or (teacher_id is not None and session["teacher_id"] != teacher_id):
        raise ServiceError("SESSION_NOT_FOUND", "课堂不存在。", 404)
    if must_be_open and session["phase"] == "scheduled":
        raise ServiceError("SESSION_NOT_STARTED", "课堂将在设定时间开始。", 409)
    if must_be_open and session["phase"] != "open":
        raise ServiceError("SESSION_CLOSED", "课堂已结束，不能继续提交。", 409)
    return session


def _scheduled_start(value):
    try:
        moment = datetime.fromisoformat(value)
        if len(value) < 16 or moment.tzinfo or moment <= datetime.now():
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ServiceError("INVALID_START_TIME", "请选择晚于当前时间的上课日期和时间。") from exc
    return moment.isoformat(" ", timespec="seconds")


def active_teachers():
    return repo.active_teachers()


def create_classroom(teacher_id, title, course_name, class_name, classroom, *, starts_at=None):
    if not 2 <= len(title) <= 60 or not 2 <= len(course_name) <= 60:
        raise ServiceError("INVALID_CLASSROOM", "课程名称和课堂主题需为 2-60 个字符。")
    if class_name and not 2 <= len(class_name) <= 60:
        raise ServiceError("INVALID_CLASSROOM", "班级名称需为 2-60 个字符。")
    if len(classroom) > 60:
        raise ServiceError("INVALID_CLASSROOM", "教室名称不能超过 60 个字符。")
    start = _scheduled_start(starts_at) if starts_at is not None else _local_time()
    with write_transaction():
        if starts_at is not None:
            teacher = repo.user(teacher_id, active_only=True)
            if teacher is None or teacher["role"] != "teacher":
                raise ServiceError("INVALID_TEACHER", "请选择有效的授课教师。")
        database = get_db()
        course = repo.course_id(database, course_name, teacher_id)
        code = secrets.token_hex(3).upper()
        session_id = repo.create_session(title, course, class_name or title, classroom, code, start)
    return session_id, code


def teacher_classrooms(teacher_id):
    return repo.teacher_sessions(teacher_id)


def all_classrooms():
    return repo.all_sessions()


def open_classrooms():
    return repo.open_sessions()


def toggle_classroom(session_id, teacher_id):
    with write_transaction():
        session = require_session(session_id, teacher_id=teacher_id)
        if session["phase"] == "scheduled":
            raise ServiceError("SESSION_NOT_STARTED", "课堂将在设定时间开始。", 409)
        status = "closed" if session["status"] == "open" else "open"
        repo.update_session_status(session_id, status, _local_time() if status == "closed" else None)
    return status


def schedule(session_id, ids, *, actor_id=None, starts_at=None):
    if not isinstance(ids, list) or any(not isinstance(item, int) for item in ids):
        raise ServiceError("INVALID_USER_IDS", "user_ids 必须是整数数组。")
    selected = sorted(set(ids))
    with write_transaction():
        session = require_session(session_id)
        if starts_at is not None:
            if session["phase"] != "scheduled":
                raise ServiceError("INVALID_START_TIME", "仅可修改待开始课堂的上课时间。")
            repo.update_session_start(session_id, _scheduled_start(starts_at))
        if selected and repo.valid_participant_ids(selected) != set(selected):
            raise ServiceError("INVALID_USER_IDS", "名单中包含无效或停用用户。")
        repo.replace_participants(session_id, selected)
        if actor_id is not None:
            audit("session.schedule", actor_id, {"session_id": session_id, "user_ids": selected})
    return selected


def roster(session_id):
    return repo.available_participants(session_id)


def enroll(session_id, user_id):
    with get_db():
        repo.add_participant(session_id, user_id)


def join_classroom(code, user_id):
    session = repo.open_session_by_code(code)
    if session is not None:
        enroll(session["id"], user_id)
    return session


def student_dashboard(user_id):
    return {"sessions": repo.open_sessions(user_id), "upcoming": repo.upcoming_sessions(user_id),
            "recent": repo.personal_records(user_id, limit=5)}


def student_history(user_id):
    records = repo.personal_records(user_id)
    journey = [{"mood": row["mood"], "time": row["created_at"][5:16]} for row in reversed(records[:30])]
    return {"records": records, "journey": journey}


def personal_records(user_id, session_id, limit):
    return repo.personal_records(user_id, session_id, min(max(limit, 1), 500))


def manual_checkin(session_id, user_id, mood, note, anonymous, *, device_id="", log=False):
    if not isinstance(session_id, int) or mood not in MOODS:
        raise ServiceError("INVALID_EMOJI", "请选择当前情绪。")
    if len(note) > 240:
        raise ServiceError("NOTE_TOO_LONG", "补充说明不能超过 240 个字符。")
    require_session(session_id, must_be_open=True)
    with get_db():
        record = repo.create_manual_checkin(session_id, user_id, mood, note, int(anonymous), device_id[:120])
        if record is None:
            raise ServiceError("SESSION_CLOSED", "课堂已结束，不能继续提交。", 409)
        repo.add_participant(session_id, user_id)
        if log:
            audit("emoji.create", user_id, {"session_id": session_id, "source": "MANUAL"})
    return record


def _counts(rows):
    return dict.fromkeys(MOODS, 0) | {row["mood"]: row["count"] for row in rows}


def classroom_summary(session_id):
    counts = _counts(repo.mood_counts(session_id=session_id))
    total = sum(counts.values())
    return {"counts": counts, "total": total, "participants": repo.distinct_participants(session_id),
            "positive_rate": round((counts["happy"] + counts["calm"]) * 100 / total) if total else 0,
            "recent": [dict(row) for row in repo.classroom_records(session_id, limit=5)],
            **classroom_insights(session_id)}


def classroom_history(session_id, teacher_id, student_id, start, end, page):
    classroom = require_session(session_id, teacher_id=teacher_id)
    first, last = _date_range(start, end, datetime.fromisoformat)
    total = repo.count_classroom_history(session_id, student_id, first, last)
    page, pages, offset = _pagination(page, total)
    return {"class_session": classroom, "students": repo.classroom_students(session_id),
            "records": repo.classroom_history(session_id, student_id, first, last, PAGE_SIZE, offset),
            "total": total, "page": page, "pages": pages}


def statistics(user, session_id):
    if session_id:
        classroom = require_session(session_id)
        if user["role"] != "admin" and (user["role"] != "teacher" or classroom["teacher_id"] != user["id"]):
            raise ServiceError("FORBIDDEN", "当前角色无权查看该课堂统计。", 403)
    user_id = user["id"] if not session_id and user["role"] != "admin" else None
    counts = _counts(repo.mood_counts(session_id=session_id or None, user_id=user_id))
    return {"counts": counts, "total": sum(counts.values())}


def realtime(user, session_id):
    require_session(session_id, teacher_id=None if user["role"] == "admin" else user["id"])
    counts = _counts(repo.mood_counts(session_id=session_id))
    return {"session_id": session_id, "counts": counts, "total": sum(counts.values()),
            "updated_at": datetime.now().isoformat(timespec="seconds")}


def _date_range(start, end, parse=date.fromisoformat):
    try:
        first, last = (parse(start) if start else None), (parse(end) if end else None)
        if first and last and first > last:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ServiceError("INVALID_DATE", "请选择有效的起止日期。") from exc
    return _date_bound(first, start), _date_bound(last, end, end=True)


def _date_bound(moment, text, *, end=False):
    if moment is None:
        return None
    if not isinstance(moment, datetime) or len(text) == 10:
        return moment.strftime("%Y-%m-%d") + (" 23:59:59" if end else " 00:00:00")
    if end and len(text) == 16:
        moment = moment.replace(second=59)
    return moment.isoformat(" ", timespec="seconds")


def statistics_options():
    return {"courses": repo.course_filters(), "classes": repo.class_filters()}


def admin_overview(start, end, course_id=None, class_name=None, *, selected_period=False):
    if not start or not end:
        raise ServiceError("INVALID_DATE", "请选择有效的起止日期。")
    first, last = _date_range(start, end)
    metrics = repo.overview_counts(course_id, class_name)
    filters = {"course_id": course_id, "class_name": class_name}
    mood_counts = _counts(repo.mood_counts(start=first, end=last, **filters))
    metrics["checkins"] = sum(mood_counts.values())
    trend_end = datetime.now().replace(microsecond=0)
    trend_start = trend_end - timedelta(hours=24)
    bucket_hours = 2
    if selected_period:
        trend_start, trend_end = datetime.fromisoformat(first), datetime.fromisoformat(last)
        bucket_hours = max(1, math.ceil((trend_end - trend_start).total_seconds() / (12 * 3600)))
    trend = {key: [0] * 12 for key in MOODS}
    for row in repo.timed_moods(trend_start.isoformat(" "), trend_end.isoformat(" "), **filters):
        moment = datetime.fromisoformat(row["created_at"])
        index = min(int((moment - trend_start).total_seconds() // (bucket_hours * 3600)), 11)
        trend[row["mood"]][index] += 1
    label_format = "%m-%d %H:%M" if selected_period else "%H:%M"
    labels = [(trend_start + timedelta(hours=i * bucket_hours)).strftime(label_format) for i in range(12)]
    return {"metrics": metrics, "mood_counts": mood_counts,
            "recent": repo.records(start=first, end=last, limit=8, **filters), "trend": trend,
            "trend_labels": labels, "trend_period": "所选时间段" if selected_period else "最近 24 小时",
            "trend_bucket_hours": bucket_hours, **statistics_options()}


PAGE_SIZE = 50


def _pagination(page, total):
    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(max(page, 1), pages)
    return page, pages, (page - 1) * PAGE_SIZE


def admin_records(mood, start, end, page, course_id=None, class_name=None):
    first, last = _date_range(start, end)
    selected = mood if mood in MOODS else None
    total = repo.count_records(selected, first, last, course_id, class_name)
    page, pages, offset = _pagination(page, total)
    return {"records": repo.records(selected, first, last, course_id=course_id, class_name=class_name,
                                     limit=PAGE_SIZE, offset=offset),
            "total": total, "page": page, "pages": pages, **statistics_options()}


def multidimensional_statistics(course, class_name, start, end):
    first, last = _date_range(start, end, datetime.fromisoformat)
    return repo.multidimensional_statistics(course or None, class_name or None, first, last)


def _local_time(value=None):
    timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else datetime.now()
    return timestamp.replace(tzinfo=None, microsecond=0).isoformat(" ")


def ingest_ai(session_id, results, threshold):
    if not isinstance(session_id, int) or not isinstance(results, list) or len(results) > 500:
        raise ServiceError("INVALID_AI_PAYLOAD", "session_id 和 results 参数无效。")
    session = repo.session(session_id)
    if session is None or session["phase"] != "open":
        raise ServiceError("SESSION_NOT_FOUND", "课堂不存在或已结束。", 404)
    accepted, rejected = [], []
    with get_db():
        for item in results:
            mood = item.get("mood") if isinstance(item, dict) else None
            mood = EXPRESSION_TO_MOOD.get(mood, mood) if isinstance(mood, str) else None
            if mood not in MOODS:
                rejected.append({"reason": "invalid_mood"})
                continue
            try:
                confidence = float(item.get("confidence"))
            except (TypeError, ValueError):
                rejected.append({"reason": "invalid_confidence"})
                continue
            if not 0 <= confidence <= 1 or confidence < threshold:
                rejected.append({"reason": "below_threshold"})
                continue
            user_id = item.get("user_id") if isinstance(item.get("user_id"), int) else None
            if user_id is not None and active_user(user_id) is None:
                rejected.append({"reason": "invalid_user"})
                continue
            try:
                created_at = _local_time(item.get("timestamp"))
            except ValueError:
                rejected.append({"reason": "invalid_timestamp"})
                continue
            record_id = repo.create_ai_checkin(session_id, mood, confidence, str(item.get("device_id", ""))[:120], created_at, user_id)
            if record_id is None:
                rejected.append({"reason": "session_closed"})
            else:
                accepted.append(record_id)
        audit("ai.ingest", None, {"session_id": session_id, "accepted": len(accepted), "rejected": len(rejected)})
    return {"accepted": accepted, "rejected": rejected, "threshold": threshold}


def _csv(headers, values):
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows([safe_csv_value(value) for value in row] for row in values)
    return output.getvalue()


def classroom_export(session_id, teacher_id):
    classroom = require_session(session_id, teacher_id=teacher_id)
    rows = repo.classroom_records(session_id, export=True)
    return _csv(["提交时间", "课堂", "参与者", "情绪", "补充说明", "匿名提交"], (
        (row["created_at"], classroom["title"], row["participant"], MOODS[row["mood"]]["label"], row["note"],
         "是" if row["is_anonymous"] else "否") for row in rows
    ))


def records_export(mood="", start="", end="", *, actor_id=None, course_id=None, class_name=None):
    first, last = _date_range(start, end)
    rows = repo.records(mood if mood in MOODS else None, first, last, course_id=course_id, class_name=class_name)
    values = [(row["created_at"], row["course_name"], row["class_name"], row["classroom"], row["title"],
               row["username"] or "", row["display_name"] or "", MOODS[row["mood"]]["label"], row["note"],
               "是" if row["is_anonymous"] else "否", row["source"], row["confidence"] or "") for row in rows]
    if actor_id is not None:
        with get_db():
            audit("emoji.export", actor_id, {"count": len(rows)})
        return _csv(["timestamp", "course", "class_name", "classroom", "session", "username", "display_name", "mood", "note", "source", "confidence"],
                    (row[:9] + row[10:] for row in values))
    return _csv(["提交时间", "课程", "班级", "教室", "课堂", "用户名", "显示名称", "情绪", "说明", "匿名", "source", "confidence"], values)
