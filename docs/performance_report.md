# Performance Verification Report (OEP-NF-001)

- **Test Case:** `TC-Perf-01`
- **Requirement:** Standard exam-start requests should complete within 2 seconds at the 90th percentile under the configured test load; the system should be evaluated with 200 concurrent exam-start requests.
- **Test:** `exam_delivery.test_nfr.NonFunctionalRequirementsTests.test_tc_perf_01_performance_200_concurrent_requests`
- **Status:** **Pending.** No measured run has been recorded. The test is skipped on SQLite, and SQLite is the only database configured in `config/settings.py` and used by the CI workflow, so the test has not yet been executed anywhere. It needs a PostgreSQL (row-locking) database.

## Method

The test creates 200 distinct student accounts and submits `POST /api/exams/{exam_id}/start/` from a `ThreadPoolExecutor` with 200 worker threads. A synchronization barrier releases the workers together before they send their requests. Each worker creates its own `APIClient` and uses a thread-local database connection. The test records each request's wall-clock latency and HTTP status.

The test reports P50, P90, P99, and error rate from the measured run. The P90 assertion is 2 seconds and all requests must return HTTP 201. The test prints a `PERF_METRICS` line containing the measured values so CI output can be retained as execution evidence.

## Results

No measured values are stated in this document because no run has been recorded yet.

| Date | Database | Runner | Python | Workers | P50 | P90 | P99 | Error rate | Outcome |
|---|---|---|---|---|---|---|---|---|---|
| Not run | PostgreSQL | - | - | 200 | - | - | - | - | Pending |

### Recording a run

1. Point `DATABASES["default"]` at a PostgreSQL database, using a local settings change that is not committed (`config/settings.py` currently defines SQLite only; `psycopg` is already in `requirements.txt`).
2. Run `python -m pytest exam_delivery/test_nfr.py -k tc_perf_01 -s`. The `-s` flag is needed to see the `PERF_METRICS` line on a passing run.
3. Replace the "Not run" row above with the values from the `PERF_METRICS` line, which also prints the database backend, runner, Python version, worker count and test date, and note whether the P90 assertion (2 seconds) passed.

Results from a developer laptop must not be represented as production capacity evidence.

## Limitations

This is a concurrent application-level integration test, not a production load test. It does not model a geographically distributed user population, browser rendering, network latency, or long-duration load. A production capacity claim requires a representative deployment and load-testing environment.
