# Online Exam Portal

A web-based portal for running online exams, built as our Software Engineering mini project. Admins manage users and courses, Faculty build question banks and exams, and Students sign up, take timed exams and see their results.

This repository holds the backend: a REST API built with Django and Django REST Framework. The full requirements and design are in the documents listed under [Project documents](#project-documents).

## Team

| Name | ID |
|---|---|
| Rehan S Bawakhan | CS820 |
| Yeshaswinie D | CS619 |
| Yashwantha R | CS614 |
| Yashaswini Singh | CS612 |

## Tech stack

- Python 3.13
- Django 5.2 and Django REST Framework 3.18
- SQLite for development (the SRS targets PostgreSQL or MySQL for deployment; the `psycopg` driver is already in `requirements.txt`)
- Argon2 password hashing
- pytest with pytest-django for tests
- GitHub Actions for CI

## Getting started

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/Yesh-2516/SE-Mini-Project.git
cd SE-Mini-Project
python -m venv .venv
```

Activate it:

- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- Windows (Git Bash): `source .venv/Scripts/activate`
- macOS / Linux: `source .venv/bin/activate`

### 2. Install dependencies and set up the database

```bash
pip install -r requirements.txt
python manage.py migrate
```

### 3. Create an admin account

```bash
python manage.py createsuperuser
```

Superusers automatically get the Admin role. Admins can then create Faculty and Student accounts through the API or the Django admin site.

### 4. Run the server

```bash
python manage.py runserver
```

- API: http://127.0.0.1:8000/api/
- Django admin: http://127.0.0.1:8000/admin/

> **Upgrading an older local copy?** Sprint 1 switched to a custom user model (`accounts.User`). If you set up the project before that, delete your local `db.sqlite3` and run `python manage.py migrate` again.

## Running the tests

```bash
python -m pytest
python manage.py check
```

CI runs both on every pull request to `main` (see `.github/workflows/django.yml`).

## Roles

| Role | Can do |
|---|---|
| **Admin** | Everything Faculty can do, plus manage Faculty/Student accounts and courses |
| **Faculty** | Manage the question bank and build exams |
| **Student** | Register, log in and view their own profile (exam-taking endpoints are in progress) |

Roles are enforced on the server for every endpoint. Requests without a valid login get **401**; a logged-in user whose role isn't allowed gets **403**.

## Using the API

### Log in

Every endpoint except register and login needs a token. Log in with a username, email or roll number:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'
```

The response contains a token and the user's role:

```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b",
  "role": "ADMIN",
  "user": { "id": 1, "username": "admin", "role": "ADMIN" }
}
```

Send the token in the `Authorization` header on later requests:

```bash
curl http://127.0.0.1:8000/api/auth/me/ \
  -H "Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
```

### Endpoints

**Authentication**: `/api/auth/`

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/auth/register/` | Anyone | Student sign-up with email and/or roll number |
| POST | `/api/auth/login/` | Anyone | Get a token and role |
| POST | `/api/auth/logout/` | Logged in | Invalidate the token |
| GET | `/api/auth/me/` | Logged in | Current user and role |

**Account management**: `/api/admin/users/`

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET, POST | `/api/admin/users/` | Admin | List (filter by `?role=`, `?is_active=`) or create Faculty/Student accounts |
| GET, PUT, PATCH | `/api/admin/users/<id>/` | Admin | View or edit an account |
| POST | `/api/admin/users/<id>/deactivate/` | Admin | Block login and revoke the token |
| POST | `/api/admin/users/<id>/activate/` | Admin | Restore access |

**Courses**: `/api/admin/courses/`

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET, POST | `/api/admin/courses/` | Admin | List or create courses |
| GET, PUT, PATCH, DELETE | `/api/admin/courses/<id>/` | Admin | View, edit or delete a course |
| POST | `/api/admin/courses/<id>/faculty/` | Admin | Map Faculty (`{"user_ids": [...]}`) |
| DELETE | `/api/admin/courses/<id>/faculty/<user_id>/` | Admin | Unmap a Faculty member |
| POST | `/api/admin/courses/<id>/students/` | Admin | Map Students (`{"user_ids": [...]}`) |
| DELETE | `/api/admin/courses/<id>/students/<user_id>/` | Admin | Unmap a Student |

**Question bank**: `/api/questions/`

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET, POST | `/api/questions/` | Faculty, Admin | List (filter by `?subject=`, `?topic=`, `?difficulty=`) or add questions |
| GET, PUT, PATCH, DELETE | `/api/questions/<id>/` | Faculty, Admin | View, edit or delete a question (locked while in a published/live exam) |
| POST | `/api/questions/import/` | Faculty, Admin | Bulk import from a `.csv` or `.xlsx` file (max 5 MB) |
| GET | `/api/questions/import/template/` | Faculty, Admin | Download the CSV import template |

Supported question types: `MCQ`, `TRUE_FALSE`, `FILL_IN_THE_BLANK`, `SHORT_ANSWER`. Difficulties: `EASY`, `MEDIUM`, `HARD`.

**Exams**: `/api/exams/`

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET, POST | `/api/exams/` | Faculty, Admin | List or create draft exams |
| GET, PUT, PATCH | `/api/exams/<id>/` | Faculty, Admin | View (with questions) or edit duration, availability window and negative marking |
| POST | `/api/exams/<id>/assemble/` | Faculty, Admin | Pick questions by ID (`{"question_ids": [...]}`) |
| POST | `/api/exams/<id>/generate/` | Faculty, Admin | Auto-generate by subject, topic and difficulty counts |
| PATCH | `/api/exams/<id>/questions/<question_id>/marks/` | Faculty, Admin | Set marks for one question |

**Exam Delivery & Sitting**: `/api/exams/<id>/`

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/api/exams/<id>/start/` | Student | Start sitting or resume in-progress exam (returns paper & timer) |
| GET | `/api/exams/<id>/attempts/<attempt_id>/` | Student, Faculty, Admin | View current sitting paper with saved answers |
| GET | `/api/exams/<id>/attempts/<attempt_id>/timer/` | Student | Server-synchronized countdown timer |
| PUT, POST | `/api/exams/<id>/attempts/<attempt_id>/autosave/` | Student | Periodically autosave answers mid-exam |
| POST | `/api/exams/<id>/attempts/<attempt_id>/submit/` | Student | Submit exam manually or on timeout (triggers objective auto-grading) |
| POST, PATCH | `/api/exams/<id>/attempts/<attempt_id>/questions/<question_id>/flag/` | Student | Toggle bookmark flag for question review |
| GET | `/api/exams/<id>/attempts/<attempt_id>/navigator/` | Student | Question status overview (answered & flagged counts) |
| POST | `/api/exams/<id>/attempts/<attempt_id>/allow-reattempt/` | Faculty, Admin | Explicitly permit a student to reattempt the exam |

**System Diagnostics**: `/api/admin/diagnostics/`

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/admin/diagnostics/` | Admin | Check server health, database connectivity, and platform metrics |


## Project status

Sprint 1 features merged into `main`:

| Module | Requirements |
|---|---|
| Authentication & access control | OEP-F-001 registration, OEP-F-002 login, OEP-F-003 role-based access, OEP-SR-002 Argon2 hashing |
| Question bank | OEP-F-010 add questions, OEP-F-011 tagging and filtering, OEP-F-012 bulk import, OEP-F-013 edit/delete with exam lock |
| Exam creation | OEP-F-020 assembly (manual or rule-based), OEP-F-021 duration and scoring, OEP-F-022 availability window |
| Exam delivery | OEP-F-030 server-synced timer, OEP-F-031 question navigation & flags, OEP-F-032 auto-submit on timeout, OEP-F-033 manual submit, OEP-F-034 single-attempt rule & reattempt, OEP-F-035 periodic autosave |
| Evaluation | OEP-F-040 objective-answer automatic grading wired to submission |
| Administration | OEP-F-060 account management, OEP-F-061 courses and mappings, OEP-F-063 health diagnostics panel |
| Non-Functional | OEP-NF-001 performance (2s / 200 concurrent), OEP-NF-002 reliability (no answer loss on disconnect, idempotent submit), OEP-NF-003 availability (99% uptime) |
| Security | OEP-SR-004 answer keys kept out of student exam data |

Upcoming features include publishing exams to courses, subjective evaluation queue, results & scorecards, account lockout and audit logging. See the [issues](https://github.com/Yesh-2516/SE-Mini-Project/issues) for the full backlog.

Implementation choices that differ from the SRS/SAD are recorded in [deviations.md](deviations.md).

## Project structure

```
SE-Mini-Project/
├── accounts/          # Custom user model, registration, login, roles, account management
├── courses/           # Courses and Faculty/Student mappings
├── question_bank/     # Questions, tagging, bulk import, objective grading
├── exam_management/   # Exams, assembly, scoring settings, availability window
├── exam_delivery/     # Exam sitting, server-synced timer, autosave, submission, diagnostics
├── docs/              # Database models, performance and availability reports
├── config/            # Django settings and root URLs
├── deviations.md      # Deviations from the SRS/SAD and integration notes
└── requirements.txt
```

## Contributing

We work in one branch and one pull request per requirement:

1. Branch from the latest `main`, named after the requirement, e.g. `feature/OEP-F-024-publish-exam`.
2. Commit with a conventional prefix: `feat:`, `fix:`, `test:`, `docs:` or `chore:`.
3. Open a pull request to `main` with a summary, test results and the requirement ID, and add `Closes #<issue>`.
4. Wait for CI to pass and for a review, then merge with **Create a merge commit**.

Before opening a pull request, run `python -m pytest` and `python manage.py check`. If your change adds or changes a model, also run `python manage.py makemigrations` and commit the migration.

## Project documents

- [Software Requirements Specification](Software%20Requirements%20Specification.docx)
- [Software Architecture and Design Specification](Software%20Architecture%20and%20Design%20Specification.docx)
- [Software Test Plan](Software%20Test%20Plan.docx)
- [Database Models Specification](docs/models.md)
- [Performance Verification Report (TC-Perf-01)](docs/performance_report.md)
- [Availability Verification Report (TC-Ops-01)](docs/availability_report.md)
