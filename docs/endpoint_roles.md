# Endpoint-to-Role List (OEP-SR-006, TC-Sec-06)

Every API endpoint and the roles the server allows to call it. Checks run on the server, in each view's `permission_classes`, so hiding something in the UI is never the only protection.

- **Anyone**: no login needed.
- **Any logged-in user**: any role with a valid token.
- Any other role gets `403`, and a request with no valid token gets `401`.

Roles are only the first check. Exam delivery also confirms that the attempt belongs to the student making the request.

`accounts/test_rbac.py` fails if this list stops matching the code, so update it whenever you add or change an endpoint.

## Authentication

| Route name | Path | Methods | Allowed roles |
|---|---|---|---|
| `auth-register` | `/api/auth/register/` | POST | Anyone |
| `auth-login` | `/api/auth/login/` | POST | Anyone |
| `auth-logout` | `/api/auth/logout/` | POST | Any logged-in user |
| `auth-me` | `/api/auth/me/` | GET | Any logged-in user |

## Administration

| Route name | Path | Methods | Allowed roles |
|---|---|---|---|
| `admin-user-list-create` | `/api/admin/users/` | GET, POST | Admin |
| `admin-user-detail` | `/api/admin/users/<int:pk>/` | GET, PUT, PATCH | Admin |
| `admin-user-deactivate` | `/api/admin/users/<int:pk>/deactivate/` | POST | Admin |
| `admin-user-activate` | `/api/admin/users/<int:pk>/activate/` | POST | Admin |
| `admin-audit-logs` | `/api/admin/users/audit-logs/` | GET | Admin |
| `course-list-create` | `/api/admin/courses/` | GET, POST | Admin |
| `course-detail` | `/api/admin/courses/<int:pk>/` | GET, PUT, PATCH, DELETE | Admin |
| `course-faculty` | `/api/admin/courses/<int:pk>/faculty/` | POST | Admin |
| `course-faculty-detail` | `/api/admin/courses/<int:pk>/faculty/<int:user_id>/` | DELETE | Admin |
| `course-students` | `/api/admin/courses/<int:pk>/students/` | POST | Admin |
| `course-student-detail` | `/api/admin/courses/<int:pk>/students/<int:user_id>/` | DELETE | Admin |
| `admin-diagnostics` | `/api/admin/diagnostics/` | GET | Admin |

## Question bank

| Route name | Path | Methods | Allowed roles |
|---|---|---|---|
| `question-import-template` | `/api/questions/import/template/` | GET | Faculty, Admin |
| `question-list-create` | `/api/questions/` | GET, POST | Faculty, Admin |
| `question-import` | `/api/questions/import/` | POST | Faculty, Admin |
| `question-detail` | `/api/questions/<int:pk>/` | GET, PUT, PATCH, DELETE | Faculty, Admin |

## Exam management

| Route name | Path | Methods | Allowed roles |
|---|---|---|---|
| `exam-list-create` | `/api/exams/` | GET, POST | Faculty, Admin |
| `exam-detail` | `/api/exams/<int:pk>/` | GET, PUT, PATCH | Faculty, Admin |
| `exam-manual-assembly` | `/api/exams/<int:pk>/assemble/` | POST | Faculty, Admin |
| `exam-rule-generation` | `/api/exams/<int:pk>/generate/` | POST | Faculty, Admin |
| `exam-question-marks` | `/api/exams/<int:pk>/questions/<int:question_id>/marks/` | PATCH | Faculty, Admin |

## Exam delivery

| Route name | Path | Methods | Allowed roles |
|---|---|---|---|
| `exam-attempt-start` | `/api/exams/<int:exam_id>/start/` | POST | Student |
| `exam-attempt-detail` | `/api/exams/<int:exam_id>/attempts/<int:attempt_id>/` | GET | Student |
| `exam-attempt-timer` | `/api/exams/<int:exam_id>/attempts/<int:attempt_id>/timer/` | GET | Student |
| `exam-attempt-autosave` | `/api/exams/<int:exam_id>/attempts/<int:attempt_id>/autosave/` | POST, PUT | Student |
| `exam-attempt-submit` | `/api/exams/<int:exam_id>/attempts/<int:attempt_id>/submit/` | POST | Student |
| `exam-attempt-flag` | `/api/exams/<int:exam_id>/attempts/<int:attempt_id>/questions/<int:question_id>/flag/` | POST, PATCH | Student |
| `exam-attempt-navigator` | `/api/exams/<int:exam_id>/attempts/<int:attempt_id>/navigator/` | GET | Student |
| `exam-attempt-allow-reattempt` | `/api/exams/<int:exam_id>/attempts/<int:attempt_id>/allow-reattempt/` | POST | Faculty, Admin |
