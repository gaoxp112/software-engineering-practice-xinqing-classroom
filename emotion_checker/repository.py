"""Parameterized SQLite operations for application services."""

from .db import get_db


def _one(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def _all(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def user(user_id, *, active_only=False):
    condition = " AND is_active = 1" if active_only else ""
    return _one("SELECT * FROM users WHERE id = ?" + condition, (user_id,))


def user_by_name(username):
    return _one("SELECT * FROM users WHERE username = ?", (username,))


def create_user(username, name, password_hash, role, email):
    return get_db().execute(
        "INSERT INTO users (username, display_name, password_hash, role, email) VALUES (?, ?, ?, ?, ?)",
        (username, name, password_hash, role, email),
    ).lastrowid


def update_password(user_id, password_hash):
    get_db().execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def toggle_user(user_id):
    return get_db().execute("UPDATE users SET is_active = NOT is_active WHERE id = ?", (user_id,)).rowcount


def users(keyword, *, search_email=False):
    sql = "SELECT u.*, COUNT(c.id) AS checkin_count FROM users u LEFT JOIN checkins c ON c.user_id = u.id"
    params = []
    if keyword:
        sql += " WHERE u.username LIKE ? OR u.display_name LIKE ?"
        params = [f"%{keyword}%"] * 2
        if search_email:
            sql += " OR u.email LIKE ?"
            params.append(f"%{keyword}%")
    return _all(sql + " GROUP BY u.id ORDER BY u.created_at DESC", params)


def audit(action, user_id, details):
    get_db().execute("INSERT INTO audit_logs (action, user_id, details) VALUES (?, ?, ?)", (action, user_id, details))


def session(session_id):
    return _one("""SELECT s.*, u.display_name AS teacher_name FROM session_details s
                   JOIN users u ON u.id = s.teacher_id WHERE s.id = ?""", (session_id,))


def open_session_by_code(code):
    return _one("SELECT id FROM session_details WHERE session_code = ? AND phase = 'open'", (code,))


def open_sessions(user_id=None):
    if user_id is None:
        counts = "(SELECT COUNT(*) FROM session_participants sp WHERE sp.session_id = s.id) AS participant_count"
        params = ()
    else:
        counts = "(SELECT COUNT(*) FROM checkins c WHERE c.session_id = s.id AND c.user_id = ?) AS my_count"
        params = (user_id,)
    return _all(f"""SELECT s.*, u.display_name AS teacher_name, {counts}
                    FROM session_details s JOIN users u ON u.id = s.teacher_id
                    WHERE s.phase = 'open' ORDER BY s.starts_at DESC""", params)


def upcoming_sessions(user_id):
    return _all("""SELECT s.*, u.display_name AS teacher_name FROM session_details s
                   JOIN session_participants p ON p.session_id = s.id JOIN users u ON u.id = s.teacher_id
                   WHERE p.user_id = ? AND s.phase = 'scheduled' ORDER BY s.starts_at""", (user_id,))


def teacher_sessions(teacher_id):
    return _all("""SELECT s.*, COUNT(c.id) AS checkin_count, COUNT(DISTINCT c.user_id) AS participant_count
                   FROM session_details s LEFT JOIN checkins c ON c.session_id = s.id
                   WHERE s.teacher_id = ? GROUP BY s.id ORDER BY s.created_at DESC""", (teacher_id,))


def all_sessions():
    return _all("""SELECT s.*, u.display_name AS teacher_name, COUNT(sp.user_id) AS participant_count
                   FROM session_details s JOIN users u ON u.id = s.teacher_id
                   LEFT JOIN session_participants sp ON sp.session_id = s.id
                   GROUP BY s.id ORDER BY s.starts_at DESC""")


def course_id(database, course_name, teacher_id):
    database.execute("INSERT INTO courses (name, teacher_id) VALUES (?, ?) ON CONFLICT(name, teacher_id) DO NOTHING",
                     (course_name, teacher_id))
    return database.execute("SELECT id FROM courses WHERE name = ? AND teacher_id = ?", (course_name, teacher_id)).fetchone()[0]


def create_session(title, course, class_name, classroom, code, starts_at):
    return get_db().execute(
        """INSERT INTO class_sessions (title, course_id, class_name, classroom, session_code, starts_at)
           VALUES (?, ?, ?, ?, ?, ?)""", (title, course, class_name, classroom, code, starts_at),
    ).lastrowid


def active_teachers():
    return _all("SELECT id, display_name, username FROM users WHERE role = 'teacher' AND is_active = 1 ORDER BY display_name, id")


def update_session_start(session_id, starts_at):
    get_db().execute("UPDATE class_sessions SET starts_at = ? WHERE id = ?", (starts_at, session_id))


def update_session_status(session_id, status, ends_at):
    get_db().execute("UPDATE class_sessions SET status = ?, ends_at = ? WHERE id = ?", (status, ends_at, session_id))


def add_participant(session_id, user_id):
    get_db().execute("INSERT OR IGNORE INTO session_participants (session_id, user_id) VALUES (?, ?)", (session_id, user_id))


def valid_participant_ids(ids):
    placeholders = ",".join("?" for _ in ids)
    return {row[0] for row in _all(f"""SELECT id FROM users WHERE id IN ({placeholders})
                                      AND is_active = 1 AND role IN ('student', 'teacher')""", ids)}


def replace_participants(session_id, ids):
    database = get_db()
    database.execute("DELETE FROM session_participants WHERE session_id = ?", (session_id,))
    database.executemany("INSERT INTO session_participants (session_id, user_id) VALUES (?, ?)",
                         [(session_id, user_id) for user_id in ids])


def available_participants(session_id):
    return _all("""SELECT u.*, CASE WHEN sp.user_id IS NULL THEN 0 ELSE 1 END AS selected
                   FROM users u LEFT JOIN session_participants sp ON sp.user_id = u.id AND sp.session_id = ?
                   WHERE u.is_active = 1 AND u.role IN ('student', 'teacher') ORDER BY u.role, u.display_name""", (session_id,))


def create_manual_checkin(session_id, user_id, mood, note, is_anonymous, device_id):
    cursor = get_db().execute(
        """INSERT INTO checkins (session_id, user_id, mood, note, is_anonymous, device_id)
           SELECT id, ?, ?, ?, ?, ? FROM session_details WHERE id = ? AND phase = 'open'""",
        (user_id, mood, note, is_anonymous, device_id, session_id),
    )
    return _one("SELECT * FROM checkins WHERE id = ?", (cursor.lastrowid,)) if cursor.rowcount else None


def create_ai_checkin(session_id, mood, confidence, device_id, created_at, user_id=None):
    cursor = get_db().execute(
        """INSERT INTO checkins (session_id, user_id, mood, is_anonymous, source, confidence, device_id, created_at)
           SELECT id, ?, ?, 1, 'AI', ?, ?, ? FROM session_details WHERE id = ? AND phase = 'open'""",
        (user_id, mood, confidence, device_id, created_at, session_id),
    )
    return cursor.lastrowid if cursor.rowcount else None


def personal_records(user_id, session_id=None, limit=None):
    sql = """SELECT c.*, s.title, s.course_name, u.display_name AS teacher_name FROM checkins c
             JOIN session_details s ON s.id = c.session_id JOIN users u ON u.id = s.teacher_id
             WHERE c.user_id = ?"""
    params = [user_id]
    if session_id is not None:
        sql += " AND c.session_id = ?"
        params.append(session_id)
    sql += " ORDER BY c.created_at DESC, c.id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return _all(sql, params)


def mood_counts(session_id=None, user_id=None, start=None, end=None, course_id=None, class_name=None):
    where, params = _filters({"c.session_id = ?": session_id, "c.user_id = ?": user_id,
                              "c.created_at >= ?": start, "c.created_at <= ?": end,
                              "s.course_id = ?": course_id, "s.class_name = ?": class_name})
    return _all("SELECT c.mood, COUNT(*) AS count" + _RECORD_SESSIONS + where + " GROUP BY c.mood", params)


def distinct_participants(session_id):
    return _one("SELECT COUNT(DISTINCT user_id) FROM checkins WHERE session_id = ?", (session_id,))[0]


def classroom_records(session_id, *, limit=None, export=False):
    ai_label = "WHEN c.source = 'AI' THEN 'AI 采样'" if not export else ""
    columns = "c.*" if limit is None else "c.mood, c.note, c.created_at"
    sql = f"""SELECT {columns}, CASE {ai_label}
                  WHEN c.is_anonymous = 1 OR c.user_id IS NULL THEN '匿名同学' ELSE u.display_name END AS participant FROM checkins c
              LEFT JOIN users u ON u.id = c.user_id WHERE c.session_id = ?"""
    params = [session_id]
    sql += " ORDER BY c.created_at" if export else " ORDER BY c.created_at DESC, c.id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return _all(sql, params)


def classroom_students(session_id):
    return _all("""SELECT DISTINCT u.id, u.username, u.display_name FROM checkins c
                   JOIN users u ON u.id = c.user_id WHERE c.session_id = ? AND c.is_anonymous = 0
                   AND c.source = 'MANUAL' AND u.role = 'student' ORDER BY u.display_name, u.id""", (session_id,))


_CLASSROOM_FEEDBACK = " FROM checkins c LEFT JOIN users u ON u.id = c.user_id"


def _classroom_history_filters(session_id, student_id, start, end):
    return _filters({"c.session_id = ?": session_id, "c.created_at >= ?": start, "c.created_at <= ?": end,
                     "c.user_id = ? AND c.is_anonymous = 0 AND c.source = 'MANUAL' AND u.role = 'student'": student_id})


def count_classroom_history(session_id, student_id, start, end):
    where, params = _classroom_history_filters(session_id, student_id, start, end)
    return _one("SELECT COUNT(*)" + _CLASSROOM_FEEDBACK + where, params)[0]


def classroom_history(session_id, student_id, start, end, limit, offset):
    where, params = _classroom_history_filters(session_id, student_id, start, end)
    return _all("""SELECT c.mood, c.note, c.created_at, c.source,
                          CASE WHEN c.source = 'AI' THEN 'AI 采样'
                               WHEN c.is_anonymous = 1 OR c.user_id IS NULL THEN '匿名同学'
                               ELSE u.display_name END AS participant""" +
                _CLASSROOM_FEEDBACK + where + " ORDER BY c.created_at DESC, c.id DESC LIMIT ? OFFSET ?",
                [*params, limit, offset])


def timed_moods(start, end, session_id=None, course_id=None, class_name=None):
    where, params = _filters({"c.created_at >= ?": start, "c.created_at <= ?": end, "c.session_id = ?": session_id,
                              "s.course_id = ?": course_id, "s.class_name = ?": class_name})
    return _all("SELECT c.mood, c.created_at" + _RECORD_SESSIONS + where, params)


def latest_checkin_time(session_id, end):
    return _one("SELECT MAX(created_at) FROM checkins WHERE session_id = ? AND created_at <= ?", (session_id, end))[0]


def overview_counts(course_id=None, class_name=None):
    where, params = _filters({"course_id = ?": course_id, "class_name = ?": class_name})
    row = _one("""SELECT (SELECT COUNT(*) FROM users) AS users, COUNT(*) AS sessions,
                         COUNT(CASE WHEN phase = 'open' THEN 1 END) AS active FROM session_details""" + where, params)
    return dict(row)


def _filters(values):
    active = [(condition, value) for condition, value in values.items() if value is not None]
    where = " WHERE " + " AND ".join(condition for condition, _ in active) if active else ""
    return where, [value for _, value in active]


_RECORD_SESSIONS = " FROM checkins c JOIN session_details s ON s.id = c.session_id"


def course_filters():
    return _all("""SELECT c.id, c.name, u.display_name AS teacher_name FROM courses c
                   JOIN users u ON u.id = c.teacher_id ORDER BY c.name, u.display_name, c.id""")


def class_filters():
    return _all("SELECT DISTINCT class_name FROM class_sessions WHERE class_name <> '' ORDER BY class_name")


def _record_filters(mood, start, end, course_id, class_name):
    return _filters({"c.mood = ?": mood, "c.created_at >= ?": start, "c.created_at <= ?": end,
                     "s.course_id = ?": course_id, "s.class_name = ?": class_name})


def count_records(mood, start, end, course_id=None, class_name=None):
    where, params = _record_filters(mood, start, end, course_id, class_name)
    return _one("SELECT COUNT(*)" + _RECORD_SESSIONS + where, params)[0]


def records(mood=None, start=None, end=None, *, course_id=None, class_name=None, limit=None, offset=0):
    where, params = _record_filters(mood, start, end, course_id, class_name)
    sql = """SELECT c.*, s.title, s.course_name, s.class_name, s.classroom, u.username, u.display_name
          """ + _RECORD_SESSIONS + " LEFT JOIN users u ON u.id = c.user_id"
    sql += where + " ORDER BY c.created_at DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend((limit, offset))
    return _all(sql, params)


def multidimensional_statistics(course, class_name, start, end):
    where, params = _filters({"s.course_name = ?": course, "s.class_name = ?": class_name,
                              "c.created_at >= ?": start, "c.created_at <= ?": end})
    return _all("""SELECT c.mood, COUNT(*) AS count, s.course_id, s.course_name, s.class_name, s.classroom, s.title
                   FROM checkins c JOIN session_details s ON s.id = c.session_id""" + where +
                " GROUP BY s.course_id, s.class_name, s.classroom, s.title, c.mood ORDER BY s.course_name, s.class_name, s.title, c.mood", params)
