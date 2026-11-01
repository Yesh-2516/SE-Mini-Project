# Architecture Review Against the SAD (OEP-NF-006, TC-Arch-01)

**Status:** Draft, awaiting team sign-off
**Reviewed code:** `main` at commit `327d6dd`
**Prepared by:** Rehan S Bawakhan (CS820)

This review checks the code against SAD §3.4–3.7 and OEP-NF-006: UI, business logic and data-access code in separate modules, and an application layer that can scale out because it keeps no per-user state in memory.

## Result

| Acceptance criterion | Result |
|---|---|
| Separate UI, service and data-access modules | **Partly met.** The backend is modular, but there is no UI yet and three modules have no service layer |
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
| UI | None | Not built yet |

Dependencies between apps run in one direction, with no cycles:

```
exam_delivery → exam_management → question_bank → accounts
courses → accounts
```

`exam_delivery` and `exam_management` also use `accounts` directly for permissions, and `exam_delivery` calls `question_bank/grading.py`.

## 2. Layering

| App | API layer (`views`, `serializers`) | Business logic | Data access |
|---|---|---|---|
| `exam_delivery` | Yes | `services.py` | Django models |
| `exam_management` | Yes | `services.py`, some in views | Django models |
| `question_bank` | Yes | In views, plus `grading.py` and `import_utils.py` | Django models, some queries in views |
| `accounts` | Yes | In views and serializers | Django models, some queries in views |
| `courses` | Yes | In views and serializers | Django models |

Django's models and ORM act as the data-access layer. The SAD doesn't require a separate repository layer, so this is acceptable.

## 3. Stateless application layer

Checked by searching all non-test code on `main`:

| Check | Finding |
|---|---|
| Module-level state | Only constants, settings and URL patterns; nothing changes at runtime |
| In-process caching | None: no `cache`, `lru_cache`, `global` or thread-local use |
| Login state | API tokens and Django sessions are stored in the database |
| Exam state | Attempts, answers and the `ends_at` deadline are stored in the database, so any server instance can handle any request |
| Local files | Bulk imports are read during the request; nothing is written to local disk |

Any number of application instances could serve the same database without sharing memory. This was checked by reading the code. No run with several instances has been done.

## 4. Gaps

| # | Gap | Impact | Recommended action |
|---|---|---|---|
| 1 | No UI in this repository | The UI half of the separation can't be reviewed, and OEP-NF-005 can't be tested | Agree who builds it, then repeat this review |
| 2 | `accounts`, `courses` and `question_bank` have no `services.py` | Business logic in views is harder to reuse and test | Move logic when these modules next change; no rewrite needed |
| 3 | The configured database is SQLite | Several instances can't share a local SQLite file, so scaling out needs a change | Configure PostgreSQL, as the SRS targets, through environment variables |
| 4 | No database connection pooling (`CONN_MAX_AGE` is not set) | The SAD lists pooling as a mitigation for peak exam load | Set it with the PostgreSQL configuration |
| 5 | No rate limiting on login | SAD §3.9 lists it as a protection. It is not implemented | Add it using a shared cache, because a per-process counter would not work across instances |
| 6 | Timer sync uses polling, not WebSocket | The SAD allows polling as a fallback, and polling is simpler to scale statelessly | Record as a deviation |
| 7 | Audit log lives in `accounts`, not its own module | Only a difference in structure | Accept |

## 5. Sign-off

| Name | Decision | Date |
|---|---|---|
| Rehan S Bawakhan (CS820) | | |
| Yeshaswinie D (CS619) | | |
| Yashwantha R (CS614) | | |
| Yashaswini Singh (CS612) | | |
