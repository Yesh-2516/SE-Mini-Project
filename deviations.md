# Sprint 1 — Deviations and Integration Notes

## 1. F-040: Automatic Objective Answer Grading

- Added `FILL_IN_THE_BLANK` as a supported question type.
- Blank or missing objective-answer submissions receive zero marks.
- Incorrect nonblank objective answers receive the configured negative marks.
- Answers are compared case-insensitively after whitespace normalization.
- Short-answer questions are excluded from automatic grading and require manual evaluation.

## 2. Temporary Authorization

- The question-bank API currently uses Django `IsAdminUser`, which checks `is_staff`.
- This is a temporary stand-in for the intended Faculty/Admin role-based authorization.
- Replace or integrate this check when the actual role implementation becomes available.
- Verify that future student-facing exam endpoints never expose correct answers.
- Question detail retrieval, update, and deletion, bulk question import, and template download are restricted to staff users.
- The permissions fix is being completed as Sprint 1 carryover; full role-based authorization remains an integration dependency.

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
