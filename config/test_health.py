import importlib.util
import io
import json
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase


def load_probe_module():
    path = Path(settings.BASE_DIR) / "deploy" / "uptime_probe.py"
    spec = importlib.util.spec_from_file_location("uptime_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uptime_probe = load_probe_module()


class HealthEndpointTests(TestCase):
    """TC-Ops-01: the public liveness check the uptime monitor polls (OEP-NF-003)."""

    url = "/health/"

    def test_reports_ok_without_logging_in(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_head_is_allowed_for_monitors(self):
        self.assertEqual(self.client.head(self.url).status_code, 200)

    def test_is_never_cached(self):
        response = self.client.get(self.url)

        self.assertIn("no-cache", response["Cache-Control"])
        self.assertIn("max-age=0", response["Cache-Control"])

    def test_rejects_writes(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_database_failure_returns_503_without_details(self):
        with patch("config.health.connection.cursor", side_effect=Exception("db password=hunter2")):
            with self.assertLogs("config.health", level="ERROR"):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})


def probe(up, latency=10.0):
    return uptime_probe.Probe(datetime.now(timezone.utc), up, 200 if up else 503, latency, "" if up else "HTTP 503")


class UptimeSummaryTests(SimpleTestCase):
    def test_uptime_is_share_of_probe_intervals_that_were_up(self):
        probes = [probe(True)] * 198 + [probe(False)] * 2

        summary = uptime_probe.summarise(probes, interval=5)

        self.assertEqual(summary["uptime_percent"], 99.0)
        self.assertEqual(summary["observed_seconds"], 1000)
        self.assertEqual(summary["downtime_seconds"], 10)

    def test_longest_outage_counts_consecutive_failures(self):
        probes = [probe(True), probe(False), probe(True), probe(False), probe(False), probe(False), probe(True)]

        summary = uptime_probe.summarise(probes, interval=2)

        self.assertEqual(summary["longest_outage_seconds"], 6)
        self.assertEqual(summary["down"], 4)

    def test_latency_percentiles_ignore_failed_probes(self):
        probes = [probe(True, latency=ms) for ms in range(1, 101)] + [probe(False, latency=2000)]

        summary = uptime_probe.summarise(probes, interval=1)

        self.assertEqual(summary["latency_p50_ms"], 51)
        self.assertEqual(summary["latency_p95_ms"], 96)
        self.assertEqual(summary["latency_max_ms"], 100)

    def test_no_probes_reports_no_uptime(self):
        self.assertIsNone(uptime_probe.summarise([], interval=5)["uptime_percent"])


class FakeResponse(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode())
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ProbeOnceTests(SimpleTestCase):
    def check(self, outcome):
        with patch.object(uptime_probe.urllib.request, "urlopen", **outcome):
            return uptime_probe.probe_once("http://portal/health/", timeout=2)

    def test_ok_body_is_up(self):
        result = self.check({"return_value": FakeResponse(200, {"status": "ok"})})
        self.assertTrue(result.up)
        self.assertEqual(result.http_status, 200)

    def test_unexpected_body_is_down(self):
        result = self.check({"return_value": FakeResponse(200, {"status": "starting"})})
        self.assertFalse(result.up)

    def test_503_is_down(self):
        error = urllib.error.HTTPError("http://portal/health/", 503, "Unavailable", None, None)
        result = self.check({"side_effect": error})
        self.assertFalse(result.up)
        self.assertEqual(result.error, "HTTP 503")

    def test_timeout_is_down(self):
        result = self.check({"side_effect": TimeoutError()})
        self.assertFalse(result.up)
        self.assertEqual(result.error, "TimeoutError")


class SqliteLockingTests(SimpleTestCase):
    def test_sqlite_transactions_take_the_write_lock_up_front(self):
        # Without this, concurrent autosaves failed with "database is locked"
        # (295 of 1,748 requests from 30 students saving every second; see
        # docs/availability_report.md). Other databases don't need it.
        database = settings.DATABASES["default"]
        if database["ENGINE"] != "django.db.backends.sqlite3":
            self.skipTest("Only applies to SQLite.")

        self.assertEqual(database["OPTIONS"].get("transaction_mode"), "IMMEDIATE")
        self.assertGreater(database["OPTIONS"].get("timeout", 5), 5)
