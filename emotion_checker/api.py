"""REST controllers for the classroom application."""

import hmac
from functools import wraps

from flask import Blueprint, Response, current_app, g, jsonify, request, session

from . import services


api_bp = Blueprint("api", __name__, url_prefix="/api")


def ok(data=None, status=200):
    return jsonify({"ok": True, "data": data if data is not None else {}}), status


def error(code, message, status=400, details=None):
    payload = {"ok": False, "error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status


@api_bp.errorhandler(services.ServiceError)
def service_error(exc):
    messages = {
        "INVALID_EMOJI": "session_id 和 mood 无效。",
        "USERNAME_EXISTS": "用户名已被使用。",
        "INVALID_ROLE": "角色必须是 student、teacher 或 admin。",
    }
    return error(exc.code, messages.get(exc.code, str(exc)), exc.status)


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _user_dict(row):
    return {
        "id": row["id"], "username": row["username"],
        "display_name": row["display_name"], "email": row["email"] or "",
        "role": row["role"], "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return error("AUTH_REQUIRED", "请先登录。", 401)
        return view(*args, **kwargs)
    return wrapped


def api_roles(*roles):
    def decorator(view):
        @wraps(view)
        @api_login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                return error("FORBIDDEN", "当前角色无权执行此操作。", 403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _record_dict(row):
    return {
        "id": row["id"], "session_id": row["session_id"], "user_id": row["user_id"],
        "mood": row["mood"], "note": row["note"], "is_anonymous": bool(row["is_anonymous"]),
        "source": row["source"], "confidence": row["confidence"],
        "device_id": row["device_id"], "created_at": row["created_at"],
    }


@api_bp.post("/auth/register")
def register():
    data = _body()
    configured = current_app.config.get("ADMIN_REGISTRATION_TOKEN", "")
    invited = bool(configured) and hmac.compare_digest(str(data.get("admin_token", "")).encode(), configured.encode())
    user = services.create_account(
        str(data.get("username", "")).strip(), str(data.get("display_name", "")).strip(),
        str(data.get("password", "")), str(data.get("role", "student")),
        email=str(data.get("email", "")).strip(), mode="api", admin_invited=invited,
    )
    return ok({"user": _user_dict(user)}, 201)


@api_bp.post("/auth/login")
def login():
    data = _body()
    user = services.authenticate(str(data.get("username", "")).strip(), str(data.get("password", "")), log=True)
    session.clear()
    session["user_id"] = user["id"]
    return ok({"user": _user_dict(user)})


@api_bp.put("/auth/password")
@api_login_required
def password():
    data = _body()
    services.change_password(g.user, str(data.get("current_password", "")), str(data.get("new_password", "")), log=True)
    return ok({"message": "密码已更新。"})


@api_bp.get("/users/me")
@api_login_required
def me():
    return ok({"user": _user_dict(g.user)})


@api_bp.get("/sessions")
@api_login_required
def list_sessions():
    return ok({"sessions": [dict(row) for row in services.open_classrooms()]})


@api_bp.post("/emoji")
@api_roles("student", "teacher")
def create_emoji():
    data = _body()
    record = services.manual_checkin(
        data.get("session_id"), g.user["id"], str(data.get("mood", "")), str(data.get("note", "")).strip(),
        bool(data.get("is_anonymous")), device_id=str(data.get("device_id", "")), log=True,
    )
    return ok({"record": _record_dict(record)}, 201)


@api_bp.get("/emoji/history")
@api_login_required
def emoji_history():
    session_filter = request.args.get("session_id", "")
    session_id = int(session_filter) if session_filter.isdecimal() else None
    rows = services.personal_records(g.user["id"], session_id, request.args.get("limit", 100, type=int))
    return ok({"records": [_record_dict(row) for row in rows]})


@api_bp.get("/emoji/statistics")
@api_login_required
def emoji_statistics():
    return ok(services.statistics(g.user, request.args.get("session_id", type=int)))


@api_bp.get("/admin/users")
@api_roles("admin")
def admin_users():
    rows = services.users(request.args.get("q", "").strip(), search_email=True)
    return ok({"users": [dict(row) for row in rows]})


@api_bp.post("/admin/sessions/<int:session_id>/schedule")
@api_roles("admin")
def schedule_users(session_id):
    data = _body()
    ids = services.schedule(session_id, data.get("user_ids", []), actor_id=g.user["id"], starts_at=data.get("starts_at"))
    return ok({"session_id": session_id, "user_ids": ids})


@api_bp.get("/admin/dashboard/realtime")
@api_roles("admin", "teacher")
def realtime():
    return ok(services.realtime(g.user, request.args.get("sessionId", type=int)))


@api_bp.get("/admin/statistics")
@api_roles("admin")
def admin_statistics():
    filters = (request.args.get(key, "").strip() for key in ("course", "class", "from", "to"))
    return ok({"rows": [dict(row) for row in services.multidimensional_statistics(*filters)]})


@api_bp.post("/ai/emoji-results")
def ai_results():
    token = request.headers.get("X-AI-Service-Token", "")
    expected = current_app.config.get("AI_SERVICE_TOKEN", "")
    if not expected or not hmac.compare_digest(token, expected):
        return error("AI_UNAUTHORIZED", "AI 服务令牌无效。", 401)
    data = _body()
    threshold = float(current_app.config.get("AI_CONFIDENCE_THRESHOLD", 0.6))
    return ok(services.ingest_ai(data.get("session_id"), data.get("results", []), threshold), 201)


@api_bp.get("/admin/emoji/export")
@api_roles("admin")
def api_export():
    return Response(
        services.records_export(actor_id=g.user["id"]), mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=emotion-checkins.csv"},
    )

@api_bp.get("/openapi.json")
def openapi():
    return jsonify({
        "openapi": "3.0.3", "info": {"title": "Emotion Checker API", "version": "1.0.0"},
        "servers": [{"url": "/api"}],
        "paths": {
            "/auth/register": {"post": {"summary": "Register a user"}},
            "/auth/login": {"post": {"summary": "Create a session"}},
            "/auth/password": {"put": {"summary": "Change password"}},
            "/users/me": {"get": {"summary": "Current user"}},
            "/sessions": {"get": {"summary": "Open class sessions"}},
            "/emoji": {"post": {"summary": "Create a manual emoji record"}},
            "/emoji/history": {"get": {"summary": "Personal emoji history"}},
            "/emoji/statistics": {"get": {"summary": "Emoji statistics"}},
            "/admin/users": {"get": {"summary": "Admin user list"}},
            "/admin/sessions/{session_id}/schedule": {"post": {"summary": "Schedule participants"}},
            "/admin/dashboard/realtime": {"get": {"summary": "Realtime classroom board"}},
            "/admin/statistics": {"get": {"summary": "Multidimensional statistics"}},
            "/admin/emoji/export": {"get": {"summary": "CSV export"}},
            "/ai/emoji-results": {"post": {"summary": "AI result ingestion"}},
        },
        "security": [{"cookieAuth": []}],
        "components": {"securitySchemes": {"cookieAuth": {"type": "apiKey", "in": "cookie", "name": "session"}, "aiServiceToken": {"type": "apiKey", "in": "header", "name": "X-AI-Service-Token"}}},
    })


@api_bp.get("/docs")
def api_docs():
    return ok({"openapi": "/api/openapi.json", "message": "使用 OpenAPI 3.0 文档描述接口。"})
