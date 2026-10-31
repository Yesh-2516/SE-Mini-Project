# Pull-request review fixes prepared

This working tree is based on the latest source branch for PR #68 (`docs/update-documentation-and-deviations`) and contains the combined implementation changes requested across PRs #65–#68.

## Files changed

- `exam_delivery/services.py`
  - Commit timeout submission before returning the expired-autosave error.
  - Commit timeout submission before rejecting a new attempt after an expired attempt.
  - Force submissions at/after `ends_at` to use `TIMEOUT`.
  - Enforce student ownership in service operations.
  - Reject response question IDs that do not belong to the attempt.
  - Consume re-attempt permission after a new attempt is successfully created.
- `exam_delivery/views.py`
  - Restrict student sitting endpoints to the `STUDENT` role.
  - Return generic degraded diagnostics status and log database exceptions server-side.
  - Handle connectivity and metric-query failures independently; unavailable metrics are `null`.
- `exam_delivery/test_delivery.py`
  - Add timeout transaction, deadline, role/ownership, question-membership, and re-attempt regression tests.
- `exam_delivery/test_diagnostics.py`
  - Add connectivity and metrics-query failure tests; assert raw exception details are not returned.
- `exam_delivery/test_nfr.py`
  - Exercise 200 exam-start requests using concurrent worker threads and report measured P50/P90/P99/error rate.
  - Describe the client-session replacement reliability test accurately.
  - Rename and clarify the 100-probe availability simulation so it is not presented as scheduled-window uptime.
- `docs/performance_report.md`, `docs/availability_report.md`, `README.md`, `deviations.md`
  - Remove unsupported performance/uptime claims and document test scope and limitations.

## Validation

`python -m compileall -q .` completed successfully. Django/DRF dependencies could not be installed in this environment because package-index network access was unavailable. Therefore the Django test suite and CI have **not** been run here; run them in the project's configured Python environment before pushing.

## Important branch note

The PRs are stacked: #66 is based on #65, #67 is based on #66, and #68 is based on #67. Apply/push changes in dependency order and rebase each child branch onto its updated parent before pushing it. Do not force-push without `--force-with-lease`, and do not merge or close any PR until CI and review pass.
