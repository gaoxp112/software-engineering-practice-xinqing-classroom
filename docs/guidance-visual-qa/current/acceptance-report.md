# Baseline Acceptance Run (2026-10-27)

Date: 2026-10-27

The current source tree was served on port 5001 for this isolated check so the
long-running demo process on port 5000 could remain available. Chromium captures
cover 1366x768 and 360x800 for the login, student dashboard, teacher classroom
list, administrator overview, and administrator classroom scheduling pages.

The teacher card visibly renders the new class name field. The administrator
schedule table renders the class / room column and remains readable on mobile
with the existing horizontal table treatment. No viewport overflow, clipped
controls, blank charts, or console-visible layout failures were observed.

Automated checks:

```text
python -m unittest discover -s tests -v  -> 19 tests, OK
python -m compileall -q emotion_checker tests -> OK
git diff --check -> OK
```

Database checks observed 17 users, 13 classroom sessions, 223 emotion records,
and 155 participant links. The additive migration exposes `class_name` and
`classroom` on all 13 existing sessions without deleting existing rows.

This is the baseline visual run for the classroom and scheduling changes, not
the final project test report. On 2026-11-03 the suite was rerun with 24/24
tests passing. The AI records view was separately checked against an isolated
database; its screenshot is `admin-records-ai-desktop.png`.
