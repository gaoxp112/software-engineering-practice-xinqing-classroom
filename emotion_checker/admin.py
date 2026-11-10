from datetime import date, timedelta

from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for

from . import services
from .security import role_required, validate_csrf


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("/")
@role_required("admin")
def overview():
    today = date.today()
    default_range = ((today - timedelta(days=7)).isoformat(), today.isoformat())
    start = request.args.get("start", default_range[0])
    end = request.args.get("end", default_range[1])
    course_id, class_name = _dimensions()
    selected_period = "start" in request.args or "end" in request.args
    try:
        overview_data = services.admin_overview(start, end, course_id, class_name, selected_period=selected_period)
    except services.ServiceError as error:
        flash(str(error), "error")
        start, end = default_range
        overview_data = services.admin_overview(start, end, course_id, class_name)
    return render_template("admin/overview.html", start_date=start, end_date=end,
                           selected_course=course_id, selected_class=class_name or "", **overview_data)


@admin_bp.get("/users")
@role_required("admin")
def users():
    keyword = request.args.get("q", "").strip()
    return _render_users(keyword)


def _render_users(keyword="", *, draft=None, create_error=None):
    return render_template("admin/users.html", users=services.users(keyword), keyword=keyword,
                           draft=draft or {}, create_error=create_error)


@admin_bp.post("/users/create")
@role_required("admin")
def create_user():
    validate_csrf()
    draft = {
        "username": request.form.get("username", "").strip(),
        "display_name": request.form.get("display_name", "").strip(),
        "role": request.form.get("role", "student"),
    }
    try:
        services.create_account(
            draft["username"], draft["display_name"], request.form.get("password", ""), draft["role"], mode="admin",
        )
    except services.ServiceError as error:
        return _render_users(draft=draft, create_error=str(error)), error.status
    flash("用户已创建。", "success")
    return redirect(url_for("admin.users"))


@admin_bp.post("/users/<int:user_id>/toggle")
@role_required("admin")
def toggle_user(user_id):
    validate_csrf()
    services.toggle_user(user_id, g.user["id"])
    flash("账号状态已更新。", "success")
    return redirect(url_for("admin.users"))


def _record_filters():
    return tuple(request.args.get(key, "").strip() for key in ("mood", "start", "end"))


def _dimensions():
    return request.args.get("course_id", type=int), request.args.get("class_name", "").strip() or None


@admin_bp.get("/records")
@role_required("admin")
def records():
    mood, start, end = _record_filters()
    course_id, class_name = _dimensions()
    data = services.admin_records(mood, start, end, request.args.get("page", 1, type=int), course_id, class_name)
    return render_template("admin/records.html", selected_mood=mood, start_date=start, end_date=end,
                           selected_course=course_id, selected_class=class_name or "", **data)


@admin_bp.route("/sessions", methods=("GET", "POST"))
@role_required("admin")
def sessions():
    if request.method == "POST":
        validate_csrf()
        try:
            session_id, _ = services.create_classroom(
                request.form.get("teacher_id", type=int),
                *(request.form.get(key, "").strip() for key in ("title", "course_name", "class_name", "classroom")),
                starts_at=request.form.get("starts_at", "").strip(),
            )
        except services.ServiceError as error:
            flash(str(error), "error")
            return redirect(url_for("admin.sessions"))
        flash("课堂已排期，请安排参与名单。", "success")
        return redirect(url_for("admin.participants", session_id=session_id))
    return render_template("admin/sessions.html", sessions=services.all_classrooms(), teachers=services.active_teachers())


@admin_bp.route("/sessions/<int:session_id>/participants", methods=("GET", "POST"))
@role_required("admin")
def participants(session_id):
    class_session = services.require_session(session_id)
    if request.method == "POST":
        validate_csrf()
        try:
            ids = [int(value) for value in request.form.getlist("user_ids")]
        except ValueError as exc:
            raise services.ServiceError("INVALID_USER_IDS", "参与名单包含无效用户。") from exc
        services.schedule(session_id, ids, starts_at=request.form.get("starts_at"))
        flash("课堂参与名单已更新。", "success")
        return redirect(url_for("admin.participants", session_id=session_id))
    return render_template("admin/participants.html", class_session=class_session, users=services.roster(session_id))


@admin_bp.get("/records/export")
@role_required("admin")
def export_records():
    course_id, class_name = _dimensions()
    return Response(
        services.records_export(*_record_filters(), course_id=course_id, class_name=class_name),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=emotion-checkins.csv"},
    )
