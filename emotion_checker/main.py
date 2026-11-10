from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from . import services
from .moods import MOODS
from .security import login_required, validate_csrf


main_bp = Blueprint("main", __name__)


@main_bp.app_context_processor
def inject_moods():
    return {"moods": MOODS}


@main_bp.route("/")
def index():
    return redirect(url_for("main.dashboard") if g.user else url_for("auth.login"))


@main_bp.route("/dashboard")
@login_required
def dashboard():
    if g.user["role"] == "teacher":
        return redirect(url_for("teacher.sessions"))
    if g.user["role"] == "admin":
        return redirect(url_for("admin.overview"))
    return render_template("student/dashboard.html", **services.student_dashboard(g.user["id"]))


@main_bp.route("/checkin/<int:session_id>", methods=("GET", "POST"))
@login_required
def checkin(session_id):
    if g.user["role"] not in ("student", "teacher"):
        abort(403)
    class_session = services.require_session(session_id)
    if class_session["phase"] == "scheduled":
        flash("课堂将在设定时间开始。", "error")
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        validate_csrf()
        try:
            services.require_session(session_id, must_be_open=True)
            services.manual_checkin(
                session_id, g.user["id"], request.form.get("mood", ""), request.form.get("note", "").strip(),
                request.form.get("is_anonymous") == "1",
            )
        except services.ServiceError as error:
            flash(str(error), "error")
            if error.code == "SESSION_CLOSED":
                return redirect(url_for("main.history"))
        else:
            flash("本次情绪已记录。", "success")
            return redirect(url_for("main.history"))
    else:
        services.enroll(session_id, g.user["id"])
    return render_template("student/checkin.html", class_session=class_session)


@main_bp.route("/join", methods=("POST",))
@login_required
def join():
    validate_csrf()
    class_session = services.join_classroom(request.form.get("session_code", "").strip(), g.user["id"])
    if class_session is None:
        flash("未找到可用的课堂代码。", "error")
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.checkin", session_id=class_session["id"]))


@main_bp.route("/history")
@login_required
def history():
    return render_template("student/history.html", **services.student_history(g.user["id"]))
