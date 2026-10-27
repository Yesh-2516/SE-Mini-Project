# Availability Verification Report (OEP-NF-003)

- **Test Case Ref:** `TC-Ops-01`
- **Requirement:** `OEP-NF-003` — The exam server shall maintain at least 99% uptime during scheduled exam windows, excluding planned maintenance.
- **Executed by:** Yashwantha R (CS614)
- **Status:** PASS

---

## 1. Test Methodology

The availability verification test (`exam_delivery.test_nfr.NonFunctionalRequirementsTests.test_tc_ops_01_availability_99_percent_uptime`) probes the server health check endpoint (`/api/admin/diagnostics/`) across 100 consecutive automated health checks:
- Verifies server responsiveness and runtime status (`operational`).
- Verifies database connectivity and latency check (`connected`).
- Computes overall uptime percentage: `(successful_probes / total_probes) * 100`.

## 2. Test Results

| Parameter | Specification | Observed Result | Status |
|---|---|---|---|
| Total Probes | 100 | 100 | Completed |
| Successful Probes (HTTP 200, Status: healthy) | $\ge$ 99 | 100 | PASS |
| Failed Probes | $\le$ 1 | 0 | PASS |
| Availability / Uptime | $\ge$ 99.0% | **100.0%** | PASS |

## 3. Conclusion

The service maintained uninterrupted availability throughout the simulation, meeting and exceeding the 99% SLA specified in `OEP-NF-003`.
