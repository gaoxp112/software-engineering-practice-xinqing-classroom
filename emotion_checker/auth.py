from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from . import services
from .security import get_csrf_token, login_required, validate_csrf


auth_bp = Blueprint("auth", __name__)


@auth_bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None if user_id is None else services.active_user(user_id)
    if user_id is not None and g.user is None:
        session.clear()


@auth_bp.app_context_processor
def inject_globals():
    return {"csrf_token": get_csrf_token}


@auth_bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        validate_csrf()
        try:
            user = services.authenticate(request.form.get("username", "").strip(), request.form.get("password", ""))
        except services.ServiceError as error:
            flash(str(error), "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            get_csrf_token()
            return redirect(url_for("main.dashboard"))
    return render_template("auth/login.html")


@auth_bp.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        validate_csrf()
        try:
            services.create_account(
                request.form.get("username", "").strip(), request.form.get("display_name", "").strip(),
                request.form.get("password", ""), request.form.get("role", "student"),
            )
        except services.ServiceError as error:
            flash(str(error), "error")
        else:
            flash("注册成功，请登录。", "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html")


@auth_bp.post("/logout")
@login_required
def logout():
    validate_csrf()
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/settings", methods=("GET", "POST"))
@login_required
def settings():
    if request.method == "POST":
        validate_csrf()
        try:
            services.change_password(g.user, request.form.get("current_password", ""), request.form.get("new_password", ""))
        except services.ServiceError as error:
            flash(str(error), "error")
        else:
            flash("密码已更新。", "success")
            return redirect(url_for("auth.settings"))
    return render_template("auth/settings.html")
