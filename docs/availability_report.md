# Availability Probe Simulation (OEP-NF-003)

- **Test Case:** `TC-Ops-01`
- **Requirement:** The service target is at least 99% uptime during scheduled exam windows, excluding planned maintenance.
- **Test:** `exam_delivery.test_nfr.NonFunctionalRequirementsTests.test_tc_ops_01_availability_100_health_probe_simulation`
- **Status:** Simulation only; it does not establish the 99% uptime target.

## Method

The test makes 100 consecutive requests to `/api/admin/diagnostics/` during one test run. A probe is counted as successful only when the endpoint returns HTTP 200 and reports `status=healthy`. The test prints the number of successful probes, total probes, observed success rate, and the single-run observation scope.

## Interpretation

The observed percentage is a **100-probe health-check success rate**, not service uptime. A short sequence of probes cannot establish availability across scheduled exam windows. To verify the 99% uptime target, retain timestamped monitoring probes throughout the actual scheduled exam windows and calculate:

`uptime = (total scheduled observation time - unplanned downtime) / total scheduled observation time * 100`

Exclude planned maintenance only when it is defined and recorded in advance. The monitoring interval, probe timeout, alert policy, and observation window must be documented with the collected evidence.

## Results

No uptime percentage is claimed by this report. Attach monitoring evidence covering the required observation period before marking OEP-NF-003 as verified.
