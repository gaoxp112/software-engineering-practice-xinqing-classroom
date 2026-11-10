# Emotion Checker REST API

The JSON API is available below `/api` and uses the same Flask session as the
web client. Every response follows `{ "ok": true, "data": ... }` or
`{ "ok": false, "error": { "code", "message" } }`.

Interactive machine-readable documentation is served at `/api/openapi.json`.
The short discovery endpoint is `/api/docs`.

## Authentication

Call `POST /api/auth/login` with JSON credentials before protected requests.
The returned session cookie is used by subsequent requests. Role checks are
performed on the server for all `/api/admin/*` routes.

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Register student or teacher; admin registration requires an invite token |
| POST | `/api/auth/login` | Create a session |
| PUT | `/api/auth/password` | Change the current user's password |
| GET | `/api/users/me` | Current user profile |
| GET | `/api/sessions` | Open classroom sessions |
| POST | `/api/emoji` | Manual emoji submission |
| GET | `/api/emoji/history` | Personal history, optionally filtered by `session_id` |
| GET | `/api/emoji/statistics` | Personal or session mood counts |
| GET | `/api/admin/users` | Admin user list and record counts |
| POST | `/api/admin/sessions/{id}/schedule` | Replace the scheduled participant list |
| GET | `/api/admin/dashboard/realtime?sessionId={id}` | Teacher/admin live classroom summary |
| GET | `/api/admin/statistics?course=&class=&from=&to=` | Multidimensional statistics |
| GET | `/api/admin/emoji/export` | UTF-8 CSV export with formula-injection protection |
| POST | `/api/ai/emoji-results` | AI result ingestion using a separate service token |

## AI service contract

Send `X-AI-Service-Token` and a body such as:

```json
{
  "session_id": 1,
  "results": [
    {"mood": "calm", "confidence": 0.91, "user_id": null,
     "timestamp": "2026-10-27T10:10:00", "device_id": "camera-1"}
  ]
}
```

The configured confidence threshold defaults to `0.6` and is controlled by
`EMOTION_AI_THRESHOLD`. Low-confidence or invalid rows are returned under
`data.rejected`; accepted records are written with `source=AI`, confidence,
timestamp, and optional anonymous user ID. Raw frames and images are never
accepted or stored by this endpoint.
