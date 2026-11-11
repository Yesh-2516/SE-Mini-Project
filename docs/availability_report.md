# Availability Report (OEP-NF-003, TC-Ops-01)

- **Requirement:** the exam server stays up at least 99% of the time during scheduled exam windows, planned maintenance aside.
- **Issue acceptance criteria:** a health check is in place; uptime during a simulated exam window is 99% or more; the method is documented.
- **Result:** 100% uptime over a 25-minute simulated exam window with 10 students sitting an exam (750 of 750 probes up). **Target met for the simulated window.**

The SRS measures the target monthly ("Uptime reports ≥99% monthly"). That needs the portal on a real server through real exam windows, and the project has no hosting yet. Run the same probe there, as described under [Measuring on the real server](#measuring-on-the-real-server).

## Health check

`GET /health/` (also `HEAD`) is public, so a monitor can call it without logging in.

| Database | Response |
|---|---|
| Answers `SELECT 1` | `200 {"status": "ok"}` |
| Fails or can't be reached | `503 {"status": "unavailable"}`. The error goes to the server log only |

It is never cached and shows nothing else. Admins who need detail use the diagnostics panel (OEP-F-063).

The older `exam_delivery.test_nfr` probe test (100 calls to the admin diagnostics endpoint inside one test run) still runs. It checks that the endpoint answers reliably, not uptime.

## Method

Uptime is measured from **outside** the server, so the server being down can't also stop the measurement. `deploy/uptime_probe.py` (standard library only):

1. Calls `/health/` every `--interval` seconds on a fixed schedule, so a slow probe doesn't stretch the window.
2. Counts a probe as **up** only for HTTP 200 with `{"status": "ok"}` within `--timeout` seconds. Anything else, including a timeout, a refused connection or a 503, is **down**.
3. Writes every probe to CSV (`started_at, up, http_status, latency_ms, error`).
4. Treats each probe as standing for the interval after it:

   `uptime % = probes up / total probes × 100`, and `downtime = probes down × interval`

5. Reports the longest outage (consecutive failed probes × interval) and response-time percentiles. The exit code is 0 only if the target is met.

A probe interval of *i* seconds can miss an outage shorter than *i*, and it can overstate one by up to *i*. Use an interval well under the outage you care about. The SRS's 1% of a 3-hour exam window is 108 seconds, so 5 seconds is plenty.

### Simulated exam window

A health check on an idle server proves little, so `deploy/exam_window_load.py` runs alongside the probe. Each student logs in through the API, starts the exam, autosaves an answer every 10 seconds, and syncs the timer every 30 seconds, like the exam page.

| Setting | Value |
|---|---|
| Date | 11 November 2026, 13:16:50 to 13:41:48 UTC |
| Server | `manage.py runserver` on Windows 11, SQLite, at commit `21c4512` |
| Data | `docs/browser_checks/seed.py` on a throwaway database |
| Students | 10, all sitting "Sample exam" (30 minutes, 4 questions) |
| Probe | Every 2 s, 1.5 s timeout, for 1,500 s (750 probes) |

Commands, with the server running on port 8800:

```bash
python deploy/exam_window_load.py http://127.0.0.1:8800 --exam 1 \
    --users student_axe,student_sitting,student_keyboard,student_resume,student_retry,student_submit_error,student_session,student_timeout,student_xss,student_mobile \
    --password 'Str0ng-Passphrase!' --duration 1500 &
python deploy/uptime_probe.py http://127.0.0.1:8800/health/ \
    --interval 2 --timeout 1.5 --duration 1500 --csv uptime.csv
```

## Results

| Measure | Result |
|---|---|
| Probes up | 750 of 750 |
| **Uptime** | **100.0%** (target 99%) |
| Downtime | 0 s |
| Longest outage | 0 s |
| `/health/` response time | median 19.0 ms, 95th percentile 28.8 ms, max 80.6 ms |
| Student requests | 2,002, of which 0 failed (1,492 autosaves) |

### Problem found and fixed

The first run of this window, on the same code before the fix, also had 100% uptime. But **3 of 2,002 student requests failed**: autosaves returned HTTP 500 with `database is locked`.

On SQLite, `transaction.atomic()` starts a *deferred* transaction, which begins as a reader. When it then tries to write while another request is writing, SQLite fails it straight away instead of waiting, because waiting could deadlock. The 30-second `timeout` setting doesn't help. Autosave reads the responses, then writes them, so concurrent saves hit this.

The fix is `'transaction_mode': 'IMMEDIATE'` in `config/settings.py`. Every transaction then takes the write lock when it starts, and waits for it, within the timeout. A one-minute stress run with 30 students saving every second showed the difference:

| | Failed requests |
|---|---|
| Before | 295 of 1,748 (17%) |
| After | 0 of 1,768 |

No answers were lost in the first run, because the exam page retries a failed save. But a student would have seen "Not saved yet". `config/test_health.py` fails if the setting is removed. PostgreSQL, the production target in the SRS, doesn't need it.

## Limits

- **Not production uptime.** One machine, one 25-minute window, the development server, and a probe on the same machine. It shows the app stays up and answers under a class-sized exam load; it doesn't cover hardware, network, or hosting failures.
- **Planned maintenance** didn't arise. On the real server, record maintenance windows in advance and leave them out of the calculation.
- 10 students is a class, not the 200 concurrent users of OEP-NF-001. Load at that scale is the performance test's job (`docs/performance_report.md`).

## Measuring on the real server

1. Run `deploy/uptime_probe.py` from a **different machine** from the server, against `https://<domain>/health/`, for each scheduled exam window. Use `--interval 5 --timeout 2` and set `--duration` to the window length.
2. Keep each window's CSV and JSON summary as the evidence.
3. For the monthly figure, add up the probes over all windows in the month: `uptime % = all probes up / all probes × 100`.
4. Leave out probes inside planned maintenance windows that were announced in advance, and say which in the report.
