# REST and Layered Architecture Supplement

`api.py` and the HTML Blueprints are Controllers. They handle request parameters,
authentication, role checks and response formatting. Both use `services.py`
for validation, ownership checks, statistics and transactions. `repository.py`
contains parameterized SQLite queries. `db.py` manages the database connection,
schema and migrations.

Each classroom has a required `class_sessions.course_id` foreign key to
`courses.id`. The `session_details` view supplies the course name and teacher
from that relation for existing pages and API responses. Startup migration
associates existing classrooms by course name and teacher while preserving IDs.

AI results enter through `/api/ai/emoji-results` using an independent service
token. The server performs confidence filtering and supports anonymous
`user_id`; raw videos and face images are not accepted or stored. Route details
are in `docs/api.md` and the machine-readable contract is `/api/openapi.json`.
