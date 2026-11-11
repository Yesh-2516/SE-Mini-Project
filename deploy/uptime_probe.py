"""Measure uptime of the exam portal over an exam window (OEP-NF-003, TC-Ops-01).

Polls the public /health/ endpoint at a fixed interval and records every
probe in a CSV file. Run it from a machine other than the server, so that
the server being down can't also stop the measurement.

    python deploy/uptime_probe.py https://exam-portal.example.edu/health/ \
        --interval 5 --duration 10800 --csv uptime.csv

Uses only the standard library. See docs/availability_report.md for the
method and how to read the results.
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Probe:
    started_at: datetime
    up: bool
    http_status: int | None
    latency_ms: float
    error: str


def probe_once(url, timeout):
    """One probe. Up means HTTP 200 with {"status": "ok"} inside the timeout."""

    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    http_status = None
    error = ""
    up = False
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            http_status = response.status
            body = json.loads(response.read().decode("utf-8"))
            up = http_status == 200 and body.get("status") == "ok"
            if not up:
                error = "unexpected body"
    except urllib.error.HTTPError as exc:
        http_status = exc.code
        error = f"HTTP {exc.code}"
    except Exception as exc:  # Timeouts, refused connections, bad JSON.
        error = type(exc).__name__
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return Probe(started_at, up, http_status, latency_ms, error)


def summarise(probes, interval):
    """Uptime is the share of probe intervals in which the server was up.

    Each probe stands for the interval that follows it, so a failed probe
    counts `interval` seconds of downtime.
    """

    total = len(probes)
    up = sum(1 for probe in probes if probe.up)

    longest_outage = current = 0
    for probe in probes:
        current = 0 if probe.up else current + 1
        longest_outage = max(longest_outage, current)

    latencies = sorted(probe.latency_ms for probe in probes if probe.up)

    def percentile(fraction):
        if not latencies:
            return None
        return latencies[min(len(latencies) - 1, int(fraction * len(latencies)))]

    return {
        "probes": total,
        "up": up,
        "down": total - up,
        "uptime_percent": round(up / total * 100, 3) if total else None,
        "observed_seconds": total * interval,
        "downtime_seconds": (total - up) * interval,
        "longest_outage_seconds": longest_outage * interval,
        "latency_p50_ms": percentile(0.50),
        "latency_p95_ms": percentile(0.95),
        "latency_max_ms": latencies[-1] if latencies else None,
    }


def run(url, interval, duration, timeout, csv_path=None, log=print):
    probes = []
    writer = None
    handle = open(csv_path, "w", newline="", encoding="utf-8") if csv_path else None
    try:
        if handle:
            writer = csv.writer(handle)
            writer.writerow(["started_at", "up", "http_status", "latency_ms", "error"])

        count = max(1, int(duration // interval))
        next_at = time.monotonic()
        for index in range(count):
            probe = probe_once(url, timeout)
            probes.append(probe)
            if writer:
                writer.writerow([
                    probe.started_at.isoformat(timespec="milliseconds"),
                    int(probe.up),
                    probe.http_status or "",
                    probe.latency_ms,
                    probe.error,
                ])
                handle.flush()
            if not probe.up:
                log(f"{probe.started_at.isoformat(timespec='seconds')} DOWN {probe.error}")

            # Keep a fixed schedule, so slow probes don't stretch the window.
            next_at += interval
            if index < count - 1:
                time.sleep(max(0.0, next_at - time.monotonic()))
    finally:
        if handle:
            handle.close()
    return probes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("url", help="Full URL of the /health/ endpoint")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between probes (default 5)")
    parser.add_argument("--duration", type=float, required=True, help="Length of the exam window in seconds")
    parser.add_argument("--timeout", type=float, default=2.0, help="Seconds before a probe counts as down (default 2)")
    parser.add_argument("--csv", help="Write every probe to this CSV file")
    parser.add_argument("--target", type=float, default=99.0, help="Uptime target in percent (default 99)")
    args = parser.parse_args(argv)

    if args.interval <= 0 or args.duration < args.interval or args.timeout <= 0:
        parser.error("interval and timeout must be positive, and duration at least one interval")
    if args.timeout >= args.interval:
        parser.error("timeout must be shorter than the interval")

    window_start = datetime.now(timezone.utc)
    probes = run(args.url, args.interval, args.duration, args.timeout, args.csv)
    window_end = datetime.now(timezone.utc)

    summary = summarise(probes, args.interval)
    summary.update({
        "url": args.url,
        "window_start": window_start.isoformat(timespec="seconds"),
        "window_end": window_end.isoformat(timespec="seconds"),
        "interval_seconds": args.interval,
        "timeout_seconds": args.timeout,
        "target_percent": args.target,
        "met_target": summary["uptime_percent"] is not None and summary["uptime_percent"] >= args.target,
    })
    print(json.dumps(summary, indent=2))
    return 0 if summary["met_target"] else 1


if __name__ == "__main__":
    sys.exit(main())
