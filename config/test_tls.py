import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.py"
PROXY_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


def load_settings(**env):
    """Evaluate settings.py with the given environment variables."""
    clean = {
        key: value
        for key, value in os.environ.items()
        if key not in ("DJANGO_TLS_ENABLED", "DJANGO_ALLOWED_HOSTS")
    }
    with patch.dict(os.environ, {**clean, **env}, clear=True):
        return runpy.run_path(str(SETTINGS_FILE))


class TlsSettingsTests(SimpleTestCase):
    """TC-Sec-01: the HTTPS settings the deployment relies on."""

    def test_https_settings_are_on_when_tls_is_enabled(self):
        settings = load_settings(DJANGO_TLS_ENABLED="1")

        self.assertTrue(settings["SECURE_SSL_REDIRECT"])
        self.assertTrue(settings["SESSION_COOKIE_SECURE"])
        self.assertTrue(settings["CSRF_COOKIE_SECURE"])
        self.assertGreater(settings["SECURE_HSTS_SECONDS"], 0)
        self.assertEqual(settings["SECURE_PROXY_SSL_HEADER"], PROXY_HEADER)

    def test_local_development_stays_on_plain_http(self):
        settings = load_settings()

        self.assertNotIn("SECURE_SSL_REDIRECT", settings)
        self.assertNotIn("SECURE_PROXY_SSL_HEADER", settings)

    def test_tls_flag_must_be_explicitly_true(self):
        settings = load_settings(DJANGO_TLS_ENABLED="0")

        self.assertNotIn("SECURE_SSL_REDIRECT", settings)

    def test_allowed_hosts_come_from_the_environment(self):
        settings = load_settings(DJANGO_ALLOWED_HOSTS="a.example.edu, b.example.edu")

        self.assertEqual(
            settings["ALLOWED_HOSTS"],
            ["a.example.edu", "b.example.edu"],
        )


@override_settings(
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=PROXY_HEADER,
    SECURE_HSTS_SECONDS=31536000,
    ALLOWED_HOSTS=["testserver"],
)
class TlsRequestTests(SimpleTestCase):
    def test_plain_http_request_is_redirected_to_https(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://testserver/api/auth/me/")

    def test_request_forwarded_over_https_is_served_with_hsts(self):
        response = self.client.get(
            "/api/auth/me/",
            headers={"x-forwarded-proto": "https"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("max-age=31536000", response["Strict-Transport-Security"])
