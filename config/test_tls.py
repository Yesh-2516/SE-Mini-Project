import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from accounts.audit import client_ip
from accounts.audit_models import AuditLog

SETTINGS_FILE = Path(__file__).resolve().parent / "settings.py"
PROXY_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
DEPLOY_ENV = {"DJANGO_TLS_ENABLED": "1", "DJANGO_SECRET_KEY": "x" * 50}
ENV_VARS = (
    "DJANGO_TLS_ENABLED",
    "DJANGO_ALLOWED_HOSTS",
    "DJANGO_SECRET_KEY",
    "DJANGO_DEBUG",
)


def load_settings(**env):
    """Evaluate settings.py with the given environment variables."""
    clean = {
        key: value
        for key, value in os.environ.items()
        if key not in ENV_VARS
    }
    with patch.dict(os.environ, {**clean, **env}, clear=True):
        return runpy.run_path(str(SETTINGS_FILE))


class TlsSettingsTests(SimpleTestCase):
    """TC-Sec-01: the HTTPS settings the deployment relies on."""

    def test_https_settings_are_on_when_tls_is_enabled(self):
        settings = load_settings(**DEPLOY_ENV)

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

    def test_deployment_refuses_to_start_without_a_secret_key(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DJANGO_SECRET_KEY"):
            load_settings(DJANGO_TLS_ENABLED="1")

    def test_deployment_uses_the_secret_key_from_the_environment(self):
        settings = load_settings(**DEPLOY_ENV)

        self.assertEqual(settings["SECRET_KEY"], "x" * 50)

    def test_debug_is_off_by_default_when_deployed(self):
        self.assertFalse(load_settings(**DEPLOY_ENV)["DEBUG"])

    def test_local_development_keeps_debug_and_the_fallback_key(self):
        settings = load_settings()

        self.assertTrue(settings["DEBUG"])
        self.assertTrue(settings["SECRET_KEY"].startswith("django-insecure-"))

    def test_debug_can_be_turned_off_locally(self):
        self.assertFalse(load_settings(DJANGO_DEBUG="0")["DEBUG"])


class ClientIpTests(SimpleTestCase):
    """Audit logs record the real client address behind the proxy."""

    def request(self, forwarded=None):
        headers = {"REMOTE_ADDR": "127.0.0.1"}
        if forwarded is not None:
            headers["HTTP_X_FORWARDED_FOR"] = forwarded
        return RequestFactory().get("/", **headers)

    @override_settings(TLS_ENABLED=True)
    def test_behind_the_proxy_the_forwarded_address_is_used(self):
        self.assertEqual(client_ip(self.request("203.0.113.9")), "203.0.113.9")

    @override_settings(TLS_ENABLED=True)
    def test_a_client_cannot_spoof_its_address_through_the_proxy(self):
        # nginx appends the address it saw after whatever the client sent.
        request = self.request("10.9.9.9, 203.0.113.9")

        self.assertEqual(client_ip(request), "203.0.113.9")

    @override_settings(TLS_ENABLED=True)
    def test_behind_the_proxy_without_the_header_falls_back(self):
        self.assertEqual(client_ip(self.request()), "127.0.0.1")

    @override_settings(TLS_ENABLED=False)
    def test_without_the_proxy_the_header_is_ignored(self):
        self.assertEqual(client_ip(self.request("203.0.113.9")), "127.0.0.1")

    def test_no_request_gives_no_address(self):
        self.assertIsNone(client_ip(None))


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


@override_settings(TLS_ENABLED=True)
class ProxiedLoginAuditTests(TestCase):
    """The reviewer's case: a client at 203.0.113.9 logs in through nginx."""

    def test_login_audit_records_the_client_not_the_proxy(self):
        User = get_user_model()
        User.objects.create_user(username="student1", password="Str0ng-Passphrase!")

        response = self.client.post(
            "/api/auth/login/",
            {"username": "student1", "password": "Str0ng-Passphrase!"},
            content_type="application/json",
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.9",
        )

        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.get(event_type="login.success")
        self.assertEqual(entry.ip_address, "203.0.113.9")
