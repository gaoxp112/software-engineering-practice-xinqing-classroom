# Database and Migration Notes

SQLite is the local relational database used for the experiment. The schema is
created from `emotion_checker/db.py` on application startup and the same
operation is safe to repeat.

`courses.teacher_id` references `users.id`. `class_sessions.course_id` is required
and references `courses.id`. The course name and teacher shown by the application
come from `session_details`, which joins the classroom and course by ID.

On startup, the migration matches legacy classrooms to courses by course name
and teacher and rebuilds the classroom table in a transaction. It retains each
classroom ID, so participation links and emotion records keep their associations.
The migration checks SQLite foreign-key integrity before committing.

Useful local checks:

```powershell
python -c "from emotion_checker import create_app; create_app()"
python -m unittest discover -s tests -v
```

Back up `instance/emotion_checker.sqlite3` before deployment. Raw camera frames
and face images have no database columns and are intentionally not persisted.
