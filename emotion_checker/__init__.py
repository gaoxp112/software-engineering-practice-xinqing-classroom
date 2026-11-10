import os
import secrets

from flask import Flask

from . import db
from .auth import auth_bp
from .main import main_bp
from .teacher import teacher_bp
from .admin import admin_bp
from .api import api_bp
from .camera import CameraWorker
from .services import ServiceError


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("EMOTION_SECRET_KEY", secrets.token_hex(32)),
        DATABASE=os.environ.get("EMOTION_DATABASE", os.path.join(app.instance_path, "emotion_checker.sqlite3")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        AI_SERVICE_TOKEN=os.environ.get("EMOTION_AI_SERVICE_TOKEN", ""),
        AI_CONFIDENCE_THRESHOLD=float(os.environ.get("EMOTION_AI_THRESHOLD", "0.6")),
        ADMIN_REGISTRATION_TOKEN=os.environ.get("EMOTION_ADMIN_REGISTRATION_TOKEN", ""),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    app.extensions["camera"] = CameraWorker(app)
    db.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "emotion-checker"}

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    @app.errorhandler(403)
    def forbidden(_error):
        return render_error("没有权限访问这个页面。", 403)

    @app.errorhandler(404)
    def not_found(_error):
        return render_error("你访问的页面不存在。", 404)

    @app.errorhandler(400)
    def bad_request(error):
        return render_error(getattr(error, "description", "请求无效。"), 400)

    @app.errorhandler(ServiceError)
    def handle_service_error(error):
        return render_error(str(error), error.status)

    with app.app_context():
        db.init_db()

    return app


def render_error(message, status):
    from flask import render_template
    return render_template("error.html", message=message, status=status), status

