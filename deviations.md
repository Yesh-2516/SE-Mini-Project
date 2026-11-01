# Sprint 1 — Deviations and Integration Notes

## 1. F-040: Automatic Objective Answer Grading

- Added `FILL_IN_THE_BLANK` as a supported question type.
- Blank or missing objective-answer submissions receive zero marks.
- Incorrect nonblank objective answers receive the configured negative marks.
- Answers are compared case-insensitively after whitespace normalization.
- Short-answer questions are excluded from automatic grading and require manual evaluation.

## 2. Authorization

- Resolved by OEP-F-003: the temporary `IsAdminUser` (`is_staff`) checks were replaced with role-based permissions from `accounts.permissions`.
- Question-bank and exam-management endpoints (including question detail, import and template download) now require the Faculty or Admin role.
- The API denies by default (`IsAuthenticated`); only register and login are public. `accounts/test_rbac.py` walks every `/api/` route and fails if one is reachable anonymously or by a Student without being explicitly allowed.
- Verify that future student-facing exam endpoints never expose correct answers.

## 3. Integration Dependencies

- The objective-grading function is implemented and tested independently.
- Integration with actual exam attempts, submitted responses, and the submission workflow remains pending the relevant teammate implementation.
- End-to-end grading has not yet been verified.

## 4. Follow-up

- Confirm these implementation choices against the SRS, SAD, and test plan.
- Update this document if review identifies additional deviations.

## 5. Authentication & Accounts (OEP-F-001 onwards)

- A custom user model `accounts.User` (`AUTH_USER_MODEL`) adds `role` (ADMIN / FACULTY / STUDENT), a unique `roll_number`, and a unique `email`.
  - Swapping the user model needs a fresh database: delete your local `db.sqlite3` and run `python manage.py migrate` once after pulling.
  - Emails are stored lowercase and roll numbers uppercase, so uniqueness is case-insensitive.
- `POST /api/auth/register/` takes `first_name`, `last_name` (optional), `email` and/or `roll_number`, and `password`. The SAD lists a single `name` field; it is split into first and last name to match Django's user model.
- The SAD lists `role` in the registration request. Public sign-up always creates a Student, and any `role` sent is ignored, so nobody can self-register as Faculty or Admin.
- The username is the email when given, otherwise the lowercased roll number.
- Password policy: Django's built-in validators (minimum 8 characters, not too similar to the user's details, not a common password, not entirely numeric).
- Status codes follow the SAD: 201 created, 409 duplicate email/roll number, 422 password policy violation, 400 other validation errors. Error bodies keep the DRF field-error format already used by the rest of the API rather than the SAD's `{status, errorCode, message}` envelope.
- Password hashing (OEP-SR-002): Argon2 (`argon2-cffi`) is the default hasher. PBKDF2 remains as a verify-only fallback, and old hashes are upgraded to Argon2 on next login. Auth views are wrapped in `sensitive_post_parameters` so passwords are masked in Django error reports.
- Login (OEP-F-002): `POST /api/auth/login/` accepts `username` or `email` (either field may hold a username, email or roll number) plus `password`, and returns `{token, role, user}`. Clients send `Authorization: Token <key>` and use `role` to open the matching dashboard; `GET /api/auth/me/` returns the current user. `POST /api/auth/logout/` deletes the token. Idle-timeout expiry (`expiresIn` in the SAD) is left to OEP-SR-003.
- Unauthenticated API requests now return 401 (not 403) because token authentication is the primary scheme; the two existing anonymous-access tests were updated accordingly.
- Account management (OEP-F-060): Admin-only endpoints under `/api/admin/users/` list, create and edit Faculty and Student accounts; `POST .../<id>/deactivate/` and `.../<id>/activate/` toggle access. Deactivation is soft (`is_active = False`): the account can no longer log in and its API token is revoked, but its records are kept. Admin accounts are not managed through this API (use `createsuperuser` / Django admin), so an admin cannot lock out other admins. An admin password reset also revokes the user's token.
- Courses (OEP-F-061): new `courses` app. Admin-only endpoints under `/api/admin/courses/` create, edit and delete courses (unique, case-insensitive `code`), and map users with `POST .../<id>/faculty/` or `.../<id>/students/` (`{"user_ids": [...]}`) and unmap with `DELETE .../<id>/faculty/<user_id>/` or `.../<id>/students/<user_id>/`. Only active users with the matching role can be mapped. Courses are not yet linked to exams or to the question-bank `subject` text; assigning exams to courses is OEP-F-024.
- Answer keys (OEP-SR-004): `exam_management.services.get_student_exam_paper()` is the only way exam questions should be served to students. It refuses to serve the paper outside the availability window (403, `ExamNotOpen`) and returns questions through `StudentExamQuestionSerializer`, which allow-lists its fields and never includes `correct_answer` (free-text question types also return no options). The student exam screen (OEP-F-030) should use this service. Callers must still check publishing and course assignment (OEP-F-024) before calling it. The project has no client-side code yet, so there is nowhere for answer keys to leak on the client.


## 6. Exam Delivery & Diagnostics (OEP-F-030 — OEP-F-035, OEP-F-063, OEP-NF-001 — OEP-NF-003)

- Implemented by **Yashwantha R (CS614)** in the `exam_delivery` app.
- **Data Models:**
  - `exam_delivery.Attempt`: tracks student exam sitting, server deadline (`ends_at`), status (`IN_PROGRESS`, `SUBMITTED`, `EXPIRED`), submission reason (`MANUAL`, `TIMEOUT`), re-attempt permission (`allow_reattempt`), and scores (`objective_score`, `subjective_score`, `total_score`, `is_graded`).
  - `exam_delivery.Response`: tracks student answer, bookmark flag (`is_flagged`), marks obtained, and feedback per question. Unique per attempt and question.
- **Server-Authoritative Countdown Timer (OEP-F-030, TC-Deliver-01):**
  - Remaining time is calculated strictly relative to the server clock (`ends_at - now`).
  - Device clock alteration or page reload on the client does not change the server timer.
  - Starting an exam while an active, unexpired sitting exists returns the current sitting (resuming with the accurate remaining countdown).
- **Auto-Submit on Timeout (OEP-F-032, TC-Deliver-03):**
  - Automatically submits when `now >= ends_at`, setting status to `SUBMITTED` and reason to `TIMEOUT`.
  - Once submitted, further attempts to autosave or alter answers return `410 Gone`.
- **Manual Submit (OEP-F-033, TC-Deliver-04):**
  - Finalizes attempt with reason `MANUAL`, closing further answer changes.
  - Automatically evaluates objective answers (MCQ, True/False, Fill in the Blank) immediately via `grade_objective_answer` (OEP-F-040).
- **Single-Attempt Rule & Re-Attempt Allowance (OEP-F-034, TC-Deliver-05):**
  - Second attempt on completed exam is rejected with `403 Forbidden` (`ExamAlreadyAttempted`).
  - Faculty or Admin can explicitly permit a re-attempt via `POST /api/exams/<id>/attempts/<attempt_id>/allow-reattempt/` (`allow_reattempt = True`).
- **Question Navigation & Flag for Review (OEP-F-031, TC-Deliver-02):**
  - Students can toggle `is_flagged` on any question via `POST /api/exams/<id>/attempts/<attempt_id>/questions/<question_id>/flag/`.
  - `GET /api/exams/<id>/attempts/<attempt_id>/navigator/` returns summary of total, answered, and flagged counts with per-question status.
- **Periodic Response Auto-Save (OEP-F-035, TC-Deliver-06):**
  - `PUT /api/exams/<id>/attempts/<attempt_id>/autosave/` accepts batch answer updates atomically without closing attempt.
  - A client-session replacement test verifies that previously autosaved answers remain persisted (`TC-Rel-01`). It does not simulate a network-layer interruption.
- **Health Diagnostics Panel (OEP-F-063, TC-Admin-04):**
  - Admin-only endpoint `GET /api/admin/diagnostics/` reports server operational status, database connectivity status, DB query latency, and live counts of active attempts, exams, and users.
- **Non-Functional Requirements:**
  - `TC-Perf-01` (OEP-NF-001): the test sends 200 exam-start requests through concurrent worker threads and reports P50/P90/P99 latency and error rate. No measured result is claimed until an actual test run is recorded.
  - `TC-Rel-01` (OEP-NF-002): autosaved responses persist across client-session replacement; idempotent submission is verified. This is not a simulated network interruption.
  - `TC-Ops-01` (OEP-NF-003): 100 consecutive probes provide a single-run health-check success rate only. Scheduled-window uptime requires timestamped monitoring evidence over the full observation period.
