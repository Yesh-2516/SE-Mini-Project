# Performance Verification Report (OEP-NF-001)

- **Test Case:** `TC-Perf-01`
- **Requirement:** Standard exam-start requests should complete within 2 seconds at the 90th percentile under the configured test load; the system should be evaluated with 200 concurrent exam-start requests.
- **Test:** `exam_delivery.test_nfr.NonFunctionalRequirementsTests.test_tc_perf_01_performance_200_concurrent_requests`
- **Status:** Pending execution in the target CI/database environment.

## Method

The test creates 200 distinct student accounts and submits `POST /api/exams/{exam_id}/start/` from a `ThreadPoolExecutor` with up to 50 worker threads. Each worker creates its own `APIClient` and uses a thread-local database connection. The test records each request's wall-clock latency and HTTP status.

The test reports P50, P90, P99, and error rate from the measured run. The P90 assertion is 2 seconds and all requests must return HTTP 201. The test prints a `PERF_METRICS` line containing the measured values so CI output can be retained as execution evidence.

## Results

No measured values are stated in this document. Populate this section from the `PERF_METRICS` line produced by an actual run, including the database backend, host/runner, worker count, and test date. Results from SQLite and a developer laptop must not be represented as production capacity evidence.

## Limitations

This is a concurrent application-level integration test, not a production load test. It does not model a geographically distributed user population, browser rendering, network latency, or long-duration load. A production capacity claim requires a representative deployment and load-testing environment.
