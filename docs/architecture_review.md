# Architecture Review Against the SAD (OEP-NF-006, TC-Arch-01)

**Status:** Draft, awaiting team sign-off
**Reviewed code:** `main` at commit `4887d11` (includes account lockout, #71, and the role-check tests, #74), plus the student website on PR #77 at `9019b82`, which isn't merged yet
**Previous review:** `main` at `327d6dd`, before the student website existed
**Prepared by:** Rehan S Bawakhan (CS820)

This review checks the code against SAD §3.4–3.7 and OEP-NF-006: UI, business logic and data-access code in separate modules, and an application layer that can scale out because it keeps no per-user state in memory.

## Result

| Acceptance criterion | Result |
|---|---|
| Separate UI, service and data-access modules | **Mostly met.** The student website (#77) is its own `web` module with a service layer. Three backend modules still have no service layer, and the Faculty and Admin screens aren't built yet |
| No per-user state in application memory | **Met** |
| Architecture review recorded | **Met** once the team signs off below |

## 1. Module structure

The SAD chooses a modular monolith. The code follows that: each module is a Django app behind one REST API.

| SAD module | Code | Status |
|---|---|---|
| Auth Service | `accounts` | Present |
| Admin Service | `accounts`, `courses`, `exam_delivery` (diagnostics) | Present, spread across apps |
| Question Bank Service | `question_bank` | Present |
| Exam Scheduling Service | `exam_management` | Present |
| Exam Delivery Service | `exam_delivery` | Present |
| Evaluation Service | `question_bank/grading.py`, `exam_delivery/services.py` | Objective grading only; subjective grading is still in the backlog |
| Reporting Service | None | Not built yet |
| Audit & Logging Service | `accounts/audit*.py` | Present |
| UI | `web` (PR #77) | Student login, dashboard and exam page. Faculty and Admin have placeholder dashboards only |

Dependencies between apps run in one direction, with no cycles:

```
web → exam_delivery → exam_management → question_bank → accounts
courses → accounts
```

`exam_delivery` and `exam_management` also use `accounts` directly for permissions, and `exam_delivery` calls `question_bank/grading.py`. `web` uses `accounts` for login and `exam_management` for the exam-window rule. No other app imports `web`, so the UI can change without touching the backend.

## 2. Layering

| App | API layer (`views`, `serializers`) | Business logic | Data access |
|---|---|---|---|
| `exam_delivery` | Yes | `services.py` | Django models |
| `exam_management` | Yes | `services.py`, some in views | Django models |
| `question_bank` | Yes | In views, plus `grading.py` and `import_utils.py` | Django models, some queries in views |
| `accounts` | Yes | In views and serializers | Django models, some queries in views |
| `courses` | Yes | In views and serializers | Django models |
| `web` (#77) | Templates, `static/`, thin views | `services.py`, reusing `exam_management.services.is_exam_open` | Django models, read through `services.py` |

In `web`, the dashboard is rendered on the server from `web/services.py`. The exam page loads no questions in its HTML: `exam.js` calls the existing delivery API for questions, autosave, the timer and submit, so all exam rules stay in `exam_delivery`.

Django's models and ORM act as the data-access layer. The SAD doesn't require a separate repository layer, so this is acceptable.

## 3. Stateless application layer

Checked by searching all non-test code on `main` and on the #77 branch:

| Check | Finding |
|---|---|
| Module-level state | Only constants, settings and URL patterns; nothing changes at runtime |
| In-process caching | None: no `cache`, `lru_cache`, `global` or thread-local use |
| Login state | API tokens and Django sessions (used by the website) are stored in the database |
| Account lockout (#71) | The failed-login count and lock time are fields on the user row, so a lock applies on every instance |
| Exam state | Attempts, answers and the `ends_at` deadline are stored in the database, so any server instance can handle any request |
| Local files | Bulk imports are read during the request; nothing is written to local disk. Website static files are gathered once at deploy time with `collectstatic`, not at runtime |

Any number of application instances could serve the same database without sharing memory. This was checked by reading the code. No run with several instances has been done.

## 4. Gaps

| # | Gap | Impact | Recommended action |
|---|---|---|---|
| 1 | The student website is only on PR #77, and Faculty and Admin screens don't exist | Until #77 merges, `main` has no UI. Faculty and Admin still use the API or the Django admin | Merge #77. Build the Faculty and Admin screens in `web` with the same pattern |
| 2 | `accounts`, `courses` and `question_bank` have no `services.py` | Business logic in views is harder to reuse and test | Move logic when these modules next change; no rewrite needed |
| 3 | The configured database is SQLite | Several instances can't share a local SQLite file, so scaling out needs a change | Configure a server database through environment variables. The SRS and SAD allow MySQL or PostgreSQL; `requirements.txt` already includes the PostgreSQL driver (`psycopg`), so PostgreSQL is the one prepared |
| 4 | No database connection pooling (`CONN_MAX_AGE` is not set) | The SAD lists pooling as a mitigation for peak exam load | Set it with the PostgreSQL configuration |
| 5 | No rate limiting on login | SAD §3.9 lists it as a protection. Account lockout (#71) now limits guesses on one account, but nothing limits how many requests a client sends or how many accounts it tries, so the gap stands | Add it using a shared cache, because a per-process counter would not work across instances |
| 6 | Timer sync uses polling, not WebSocket | The SAD allows polling as a fallback, and polling is simpler to scale statelessly | Record as a deviation |
| 7 | Audit log lives in `accounts`, not its own module | Only a difference in structure | Accept |

## 5. Sign-off

| Name | Decision | Date |
|---|---|---|
| Rehan S Bawakhan (CS820) | | |
| Yeshaswinie D (CS619) | | |
| Yashwantha R (CS614) | | |
| Yashaswini Singh (CS612) | | |
