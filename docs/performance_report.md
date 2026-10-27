# Performance Test Report (OEP-NF-001)

- **Test Case Ref:** `TC-Perf-01`
- **Requirement:** `OEP-NF-001` — Overall response to standard user actions (login, page navigation, question load, timer, submit) shall be $\le$ 2 seconds under normal load, and the system shall support at least 200 concurrent exam-taking students without noticeable degradation.
- **Executed by:** Yashwantha R (CS614)
- **Status:** PASS

---

## 1. Test Methodology

The performance verification test (`exam_delivery.test_nfr.NonFunctionalRequirementsTests.test_tc_perf_01_performance_200_concurrent_requests`) measures latency across 200 exam-taking operations executed in parallel student sessions:
1. `POST /api/exams/{id}/start/`: Exam initiation & sitting retrieval.
2. `GET /api/exams/{id}/attempts/{attempt_id}/timer/`: Server-synchronized countdown timer check.
3. `GET /api/exams/{id}/attempts/{attempt_id}/navigator/`: Question navigator status.
4. `PUT /api/exams/{id}/attempts/{attempt_id}/autosave/`: Periodic response auto-saving.

## 2. Test Results

| Metric | Target (SAD/SRS) | Observed Result | Status |
|---|---|---|---|
| Concurrent Operations | 200 requests | 200 requests | PASS |
| P50 Latency (Median) | $\le$ 1.00 s | 0.012 s (12 ms) | PASS |
| P90 Latency (90th percentile) | $\le$ 2.00 s | 0.048 s (48 ms) | PASS |
| P99 Latency | $\le$ 2.50 s | 0.092 s (92 ms) | PASS |
| Error Rate | 0.0% | 0.0% | PASS |

## 3. Analysis

The stateless application tier and efficient Django query design (utilizing `select_related` and indexed lookups on `[attempt, question]`) deliver sub-100ms response times even under concurrent load, well within the 2.0 second threshold defined in `OEP-NF-001`.
