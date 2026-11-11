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

- F-040 objective grading is integrated with submitted exam attempts. Objective responses are automatically evaluated and objective scores are stored during submission.
- F-043 final-score calculation is implemented independently in the `evaluation` app.
- Integration of F-043 with faculty subjective evaluation (F-042) remains pending.
- End-to-end final-score calculation for mixed objective and subjective exams must be verified after F-042 integration.

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
- Login (OEP-F-002): `POST /api/auth/login/` accepts `username` or `email` (either field may hold a username, email or roll number) plus `password`, and returns `{token, role, user}`. Clients send `Authorization: Token <key>` and use `role` to open the matching dashboard; `GET /api/auth/me/` returns the current user. `POST /api/auth/logout/` deletes the token.
- Unauthenticated API requests now return 401 (not 403) because token authentication is the primary scheme; the two existing anonymous-access tests were updated accordingly.
- Account management (OEP-F-060): Admin-only endpoints under `/api/admin/users/` list, create and edit Faculty and Student accounts; `POST .../<id>/deactivate/` and `.../<id>/activate/` toggle access. Deactivation is soft (`is_active = False`): the account can no longer log in and its API token is revoked, but its records are kept. Admin accounts are not managed through this API (use `createsuperuser` / Django admin), so an admin cannot lock out other admins. An admin password reset also revokes the user's token.
- Courses (OEP-F-061): new `courses` app. Admin-only endpoints under `/api/admin/courses/` create, edit and delete courses (unique, case-insensitive `code`), and map users with `POST .../<id>/faculty/` or `.../<id>/students/` (`{"user_ids": [...]}`) and unmap with `DELETE .../<id>/faculty/<user_id>/` or `.../<id>/students/<user_id>/`. Only active users with the matching role can be mapped. Courses are not yet linked to exams or to the question-bank `subject` text; assigning exams to courses is OEP-F-024.
- Session expiry (OEP-SR-003): API tokens expire after 30 minutes without a request (`TOKEN_IDLE_TIMEOUT_MINUTES`; the SRS only says "configurable"). Login returns the timeout as `expires_in`, snake_case like the rest of this API rather than the SAD's `expiresIn`. Each authenticated request extends the session, recorded at most once a minute. An expired token is deleted and returns `401`; logging in afterwards issues a new token rather than reviving the old one. Each user has one token, so logging out ends the session on all of that user's devices. Django admin sessions use the same idle timeout. The future exam screen must call the timer or autosave endpoint more often than the timeout so a sitting never goes idle.
- HTTPS (OEP-SR-001): TLS ends at nginx (`deploy/nginx.conf`), which allows only TLS 1.2 and 1.3. Django's HTTPS redirect, HSTS and secure cookies are opt-in through `DJANGO_TLS_ENABLED=1`, so local development stays on plain HTTP. With TLS on, `DJANGO_SECRET_KEY` is required and `DEBUG` defaults to off. HSTS covers this host only: the subdomain and preload checks are silenced because they would affect the whole institution's domain. Audit logs take the client IP from the last `X-Forwarded-For` entry only while TLS is on, since otherwise any client could set the header.
- Account lockout (OEP-F-004, OEP-SR-005): five consecutive failed logins lock an account for 15 minutes (`ACCOUNT_LOCKOUT_THRESHOLD` and `ACCOUNT_LOCKOUT_DURATION` in settings; the SRS only says "temporarily"). While locked, login returns `423` even with the correct password, as the SAD specifies. A successful login resets the count. The check sits in the authentication backend, so the Django admin login is covered too. Each lockout writes an `account.locked` audit entry with the account, IP and lock expiry. Because `423` is only returned for real accounts, it reveals that an account exists; this follows the SAD. Failed logins on deactivated accounts are not counted.
- Website (OEP-F-030, OEP-NF-005): the `web` app serves login, a dashboard and the student exam page using Django templates and Bootstrap. It logs in with a Django session rather than an API token, through the same backend, so lockout and idle expiry still apply. The exam page calls the existing delivery API, so all timing, saving and grading stays on the server. Until OEP-F-024 adds publishing and course assignment, every open exam with questions is listed for every student. The timer is kept in sync by polling every 30 seconds, the SAD's fallback, rather than by WebSocket. Faculty and Admin only see a placeholder dashboard for now. Bootstrap loads from a CDN, and production will need static files served for `web/static/`.
- Answer keys (OEP-SR-004): `exam_management.services.get_student_exam_paper()` is the only way exam questions should be served to students. It refuses to serve the paper outside the availability window (403, `ExamNotOpen`) and returns questions through `StudentExamQuestionSerializer`, which allow-lists its fields and never includes `correct_answer` (free-text question types also return no options). The student exam screen (OEP-F-030) should use this service. Callers must still check publishing and course assignment (OEP-F-024) before calling it. The project has no client-side code yet, so there is nowhere for answer keys to leak on the client.

## 6. F-043: Final Attempt Score Calculation

- Created a separate `evaluation` Django app to handle final-score calculation.
- Implemented `finalize_attempt_score(attempt)` in `evaluation/services.py`.
- Only submitted attempts can be finalized. IN_PROGRESS and EXPIRED attempts are rejected.
- Finalization waits until every subjective question in the exam has a corresponding response that has been evaluated.
- Missing subjective response records also prevent finalization.
- A response is considered pending if `evaluated_at` or `marks_obtained` is NULL. Zero marks are valid evaluated marks.
- Objective scores are taken from the stored `Attempt.objective_score`; they are not recalculated.
- Subjective marks are summed and added to the objective score. Both subjective and total scores are rounded to two decimal places using ROUND_HALF_UP.
- The service updates `subjective_score`, `total_score`, and `is_graded`.
- Repeated calls recalculate the final score, allowing faculty regrading.
- Objective-only exams can be finalized with a subjective score of zero.
- The service uses transaction.atomic() and select_for_update() to protect finalization. SQLite does not enforce select_for_update() row locking; production concurrency behavior should be verified with PostgreSQL.

### F-042 Integration Contract

- F-042 must save `marks_obtained`, `feedback`, `evaluated_by`, and `evaluated_at` when faculty evaluates a subjective response.
- F-042 must validate awarded marks against the question's maximum marks.
- F-042 must call `finalize_attempt_score(attempt)` after saving subjective evaluation, within the same transaction.
- The function must also be called after regrading.
- Other workflows must not independently update `subjective_score`, `total_score`, or `is_graded`.
- Student scorecards must check `is_graded` before displaying `total_score`.
- For mixed exams, the final total remains unfinalized until all subjective responses have been evaluated.

### Verification

- Evaluation test file: 13 passed.
- Full project test suite: 259 passed, 160 subtests passed.
- No new database models or migrations were introduced for F-043.

## 7. Exam Delivery & Diagnostics (OEP-F-030 – OEP-F-035, OEP-F-063, OEP-NF-001 – OEP-NF-003)

- Implemented by **Yashwantha R (CS614)** in the `exam_delivery` app.
- **Data Models:**
  - `exam_delivery.Attempt`: tracks student exam sitting, server deadline (`ends_at`), status (`IN_PROGRESS`, `SUBMITTED`, `EXPIRED`), submission reason (`MANUAL`, `TIMEOUT`), re-attempt permission (`allow_reattempt`), and scores (`objective_score`, `subjective_score`, `total_score`, `is_graded`).
  - `exam_delivery.Response`: tracks student answer, bookmark flag (`is_flagged`), marks obtained, and feedback per question. Unique per attempt and question.
- **Server-Authoritative Countdown Timer (OEP-F-030, TC-Deliver-01):**
  - Remaining time is calculated strictly relative to the server clock (`ends_at - now`).
  - Device clock alteration or page reload on the client does not change the server timer.
  - Starting an exam while an active, unexpired sitting exists returns the current sitting (resuming with the accurate remaining countdown).
- **True/False options (OEP-SR-004):** start, resume and attempt-detail responses always return `["True", "False"]` as the options of a True/False question, whatever is stored on the question. The question bank does not require options on True/False questions, and before this change a question saved without them was returned with no options, so the exam page (`web/static/web/exam.js`, which shows radio buttons only when `options` is non-empty) displayed a text box. MCQ options are returned as stored (shuffled per attempt) and the other types get none.
- **Auto-Submit on Timeout (OEP-F-032, TC-Deliver-03):**
  - Auto-submit is **lazy**: it happens only when an attempt past `ends_at` is next touched, through the start (resume), attempt-detail, timer, autosave or submit endpoints. The attempt is then set to `SUBMITTED` with reason `TIMEOUT` and its objective answers are graded.
  - Nothing sweeps expired attempts. There is no scheduled job or background worker, so an expired attempt that nobody opens stays `IN_PROGRESS` in the database with no score until it is next accessed, and the diagnostics `active_attempts` count includes such attempts. A periodic sweep (for example a management command run by a scheduler) is not implemented.
  - The deadline is still enforced meanwhile: `ends_at` is set on the server, answers sent after it are ignored, and `remaining_seconds` is `0`.
  - Once submitted, further attempts to autosave or alter answers return `410 Gone`.
- **Manual Submit (OEP-F-033, TC-Deliver-04):**
  - Finalizes attempt with reason `MANUAL`, closing further answer changes.
  - Automatically evaluates objective answers (MCQ, True/False, Fill in the Blank) immediately via `grade_objective_answer` (OEP-F-040).
- **Single-Attempt Rule & Re-Attempt Allowance (OEP-F-034, TC-Deliver-05):**
  - Second attempt on completed exam is rejected with `403 Forbidden` (`ExamAlreadyAttempted`).
  - Simultaneous Start requests cannot create two attempts: the check and the insert run in one transaction under a row lock on the student, and a partial unique constraint (`unique_active_attempt_per_exam_student`, migration `0002`) allows only one `IN_PROGRESS` attempt per exam and student. A request that loses the race resumes the winning attempt. Row locks are ignored on SQLite, which serialises writers itself, so the constraint is the protection there.
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
  - `TC-Perf-01` (OEP-NF-001): the test sends 200 exam-start requests through concurrent worker threads and reports P50/P90/P99 latency and error rate. No measured result is claimed until an actual test run is recorded: the run is still pending, because the test is skipped on SQLite, the only database configured in `config/settings.py` and used by CI. See `docs/performance_report.md`.
  - `TC-Rel-01` (OEP-NF-002): autosaved responses persist across client-session replacement; idempotent submission is verified. This is not a simulated network interruption.
  - `TC-Ops-01` (OEP-NF-003): 100 consecutive probes provide a single-run health-check success rate only. Scheduled-window uptime requires timestamped monitoring evidence over the full observation period.

## 8. Subjective Evaluation and Scorecards (OEP-F-041, OEP-F-042, OEP-F-050)

- Implemented in the `evaluation` app (`subjective.py`, `scorecard.py`, `views.py`, `urls.py`). No new models or migrations: the existing `Response` fields (`marks_obtained`, `feedback`, `evaluated_by`, `evaluated_at`) are used.
- **Grading queue (F-041):** `GET /api/evaluation/pending/` (Faculty, Admin) returns pending subjective responses grouped per exam; `?exam_id=` narrows it to one exam. A response is pending while its attempt is submitted, it is not an objective type, and `evaluated_at` or `marks_obtained` is empty. This matches the pending rule in `finalize_attempt_score`, so a graded response leaves the queue.
- **Deviation:** exams are not linked to courses or to a faculty owner yet (OEP-F-024), so "the relevant faculty member" cannot be resolved. Every Faculty and Admin user sees all pending responses. Once exams are assigned to courses, filter the queue by the faculty member's courses in `get_grading_queue`.
- **Evaluate (F-042):** `PATCH /api/evaluation/responses/<response_id>/` with `marks` (required, two decimal places) and `feedback` (optional). Marks must be between 0 and the question's marks in that exam, otherwise `400`. Objective responses are rejected (`400`) and responses of attempts that are not submitted return `409`. Omitting `feedback` keeps the existing feedback; sending an empty string clears it. Re-evaluating a response is allowed (regrading) and is reported as `regraded: true`.
- `evaluate_response` calls `finalize_attempt_score` in the same transaction, which completes the F-042 integration contract in section 6. The response body reports `attempt.finalized` and the pending count, plus the final scores once the attempt is complete.
- **Scorecard (F-050):** `GET /api/results/<attempt_id>/` returns total, objective and subjective score, the maximum score and per-question marks, answers and feedback. It returns `409` until the attempt `is_graded`, and `403` for any student other than the owner. `GET /api/results/` lists the student's own graded attempts. Correct answers are never included (OEP-SR-004).
- The scorecard is an API only; there is no page for it in the `web` app yet.

## 9. Reports, Export and Question Breakdown (OEP-F-051, OEP-F-052, OEP-F-053)

- Implemented in the new `reports` app (`services.py`, `exports.py`, `views.py`, `urls.py`). No models or migrations.
- **Class report (F-051):** `GET /api/reports/exams/<exam_id>/` (Faculty, Admin) returns the average, highest and lowest score, the maximum score, a 10-bucket distribution (0-10% ... 90-100%; lower bound inclusive, upper exclusive, 100% joins the last bucket) and the per-student results, best score first.
- **Deviation:** the report is per exam, not per course. Exams are not linked to courses yet (OEP-F-024), so a course-level report cannot be built. Add a course filter once exams are assigned to courses.
- Only each student's most recent submitted and fully graded attempt counts. Attempts still waiting for evaluation are not counted and are reported as `pending_evaluation`. Averages are rounded to two decimals (ROUND_HALF_UP). An exam with no graded results returns `null` for average, highest and lowest.
- **Export (F-052):** `GET /api/reports/exams/<exam_id>/export/?export_format=pdf|xlsx` (Faculty, Admin) downloads the report. The parameter is `export_format` because Django REST framework reserves `format`. Both files are built from the same data as the on-screen report, so they always match. The Excel file has Summary, Distribution and Results sheets; text cells are always stored as text, so a name starting with `=` can never become a formula. The PDF is generated directly (fixed-width text, paginated) so no new package is needed; characters outside Latin-1 appear as `?` in the PDF but are kept in Excel. Only this report is exportable for now; the question breakdown is not.
- **Question breakdown (F-053):** `GET /api/reports/exams/<exam_id>/questions/` is restricted to Faculty (Admin gets 403), as the acceptance criteria say. "Got it right" means full marks on the question, for every question type; `average_marks` shows partial credit. Answer keys are never included. Like F-041, no faculty-to-exam link exists yet, so every Faculty user can open the breakdown of any exam.

## 10. Audit Logging and Retention (OEP-NF-004)

- `AuditLog` (existing model) is now append-only: editing or deleting an entry, or using `update()` / `delete()` / `bulk_update()` on the queryset, raises `AuditLogImmutable`. No migration was needed.
- The four action types are logged with the user (`actor`), action (`event_type`) and timestamp (`created_at`): logins (`login.success`, plus the existing `account.locked`), submissions (`exam.submitted`), evaluation changes (`evaluation.updated`, including previous and new marks) and integrity flags (`integrity.flag`). Only IDs, scores and reasons are logged; answers and feedback text never are.
- **Deviation:** camera/biometric proctoring is out of scope, so no client-side integrity signal exists. Integrity flags are the events the server can detect itself: a student reaching for another student's attempt (`foreign_attempt_access`) and a blocked second attempt (`second_attempt_blocked`). `record_integrity_flag()` in `accounts/audit.py` is the single place to add more. Admins can review them with `?event_type=integrity.flag`.
- **Retention:** `AUDIT_LOG_RETENTION_DAYS` (default 400, environment variable of the same name) is raised to 365 if set lower, so an entry is never kept for less than a year. `purge_expired()` refuses a cutoff inside the retention period.
- **Archival:** `python manage.py archive_audit_logs [--archive-dir DIR] [--dry-run]` writes entries older than the retention period to a JSON Lines file, checks the line count, then removes them and logs an `audit.archived` entry. It is not scheduled automatically: run it from cron, e.g. weekly.
- **Retrieval:** `GET /api/admin/users/audit-logs/` (Admin) now accepts `event_type`, `actor`, `since`, `until` (ISO date or date-time), `limit` (default 100, at most 500) and `offset`.
- Deleting a user would still set `actor` to null on that user's entries (a database-level cascade). Accounts are deactivated rather than deleted in this system, so this does not happen in normal use.
