import json

from flask import Blueprint, Response, abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for

from . import services
from .security import role_required, validate_csrf


teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


def get_owned_session(session_id):
    return services.require_session(session_id, teacher_id=g.user["id"])


@teacher_bp.route("/sessions", methods=("GET", "POST"))
@role_required("teacher")
def sessions():
    if request.method == "POST":
        validate_csrf()
        starts_at = request.form.get("starts_at", "").strip() or None
        try:
            _, code = services.create_classroom(
                g.user["id"], request.form.get("title", "").strip(), request.form.get("course_name", "").strip(),
                request.form.get("class_name", "").strip(), request.form.get("classroom", "").strip(),
                starts_at=starts_at,
            )
        except services.ServiceError as error:
            flash(str(error), "error")
        else:
            status = "课堂已预约，将在设定时间开放" if starts_at else "课堂已创建"
            flash(f"{status}，加入代码为 {code}。", "success")
            return redirect(url_for("teacher.sessions"))
    return render_template("teacher/sessions.html", sessions=services.teacher_classrooms(g.user["id"]))


@teacher_bp.route("/sessions/<int:session_id>")
@role_required("teacher")
def session_detail(session_id):
    class_session = get_owned_session(session_id)
    summary = services.classroom_summary(session_id)
    return render_template(
        "teacher/session_detail.html",
        class_session=class_session, records=summary["recent"], counts=summary["counts"], total=summary["total"],
        participant_count=summary["participants"], positive_rate=summary["positive_rate"],
        timeline=summary["timeline"], advice=summary["advice"],
        camera=current_app.extensions["camera"].status(session_id),
    )

@teacher_bp.route("/sessions/<int:session_id>/camera", methods=("GET", "POST"))
@role_required("teacher")
def session_camera(session_id):
    class_session = get_owned_session(session_id)
    camera = current_app.extensions["camera"]
    is_open = class_session["phase"] == "open"
    if request.method == "GET":
        return jsonify(is_open=is_open, **camera.status(session_id))

    validate_csrf()
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    action = request.form.get("action")
    if action == "stop":
        camera.stop(session_id)
    elif action == "start":
        if not is_open:
            flash("请先开放课堂。", "error")
        elif not camera.start(session_id):
            flash("摄像头正在另一个课堂中使用。", "error")
    else:
        abort(400, "请选择开始或停止识别。")
    return redirect(url_for("teacher.session_detail", session_id=session_id))


@teacher_bp.get("/sessions/<int:session_id>/camera/preview")
@role_required("teacher")
def camera_preview(session_id):
    if request.remote_addr not in ("127.0.0.1", "::1"):
        abort(403)
    class_session = get_owned_session(session_id)
    preview = current_app.extensions["camera"].preview(session_id) if class_session["phase"] == "open" else None
    if preview is None:
        return Response(status=204, headers={"Cache-Control": "no-store"})
    jpeg, prediction = preview
    return Response(jpeg, mimetype="image/jpeg", headers={
        "Cache-Control": "no-store",
        "Cross-Origin-Resource-Policy": "same-origin",
        "X-Camera-Detection": json.dumps(prediction, separators=(",", ":")),
    })


@teacher_bp.get("/sessions/<int:session_id>/summary")
@role_required("teacher")
def session_summary(session_id):
    get_owned_session(session_id)
    return jsonify(services.classroom_summary(session_id))


@teacher_bp.get("/sessions/<int:session_id>/records")
@role_required("teacher")
def session_records(session_id):
    student_id = request.args.get("student_id", type=int)
    start, end = (request.args.get(key, "").strip() for key in ("start", "end"))
    history = services.classroom_history(session_id, g.user["id"], student_id, start, end,
                                         request.args.get("page", 1, type=int))
    return render_template("teacher/records.html", selected_student=student_id, start=start, end=end, **history)


@teacher_bp.post("/sessions/<int:session_id>/toggle")
@role_required("teacher")
def toggle_session(session_id):
    validate_csrf()
    status = services.toggle_classroom(session_id, g.user["id"])
    if status == "closed":
        current_app.extensions["camera"].stop(session_id)
    flash("课堂状态已更新。", "success")
    return redirect(url_for("teacher.session_detail", session_id=session_id))


@teacher_bp.get("/sessions/<int:session_id>/export")
@role_required("teacher")
def export_session(session_id):
    return Response(
        services.classroom_export(session_id, g.user["id"]), mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=session-{session_id}-checkins.csv"},
    )
