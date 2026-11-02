from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = "Str0ng-Passphrase!"


class SessionExpiryTests(APITestCase):
    """TC-Sec-03: tokens expire when idle and end immediately on logout."""

    me_url = "/api/auth/me/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="prof.iyer",
            password=PASSWORD,
            role=User.Role.FACULTY,
        )
        self.login_response = self.login()
        self.token = self.login_response.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

    def login(self):
        return self.client.post(
            "/api/auth/login/",
            {"username": "prof.iyer", "password": PASSWORD},
            format="json",
        )

    def go_idle(self, **age):
        """Pretend the last request happened ``age`` ago."""
        past = timezone.now() - timedelta(**age)
        User.objects.filter(pk=self.user.pk).update(last_activity_at=past)
        Token.objects.filter(user=self.user).update(created=past)

    def test_login_reports_the_idle_timeout(self):
        self.assertEqual(self.login_response.data["expires_in"], 1800)

    def test_token_works_before_the_timeout(self):
        self.go_idle(minutes=29)

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_idle_token_is_rejected(self):
        self.go_idle(minutes=31)

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_idle_token_is_deleted_so_it_stays_rejected(self):
        self.go_idle(minutes=31)

        self.client.get(self.me_url)

        self.assertFalse(Token.objects.filter(key=self.token).exists())

    def test_each_request_extends_the_session(self):
        self.go_idle(minutes=20)
        self.client.get(self.me_url)

        self.user.refresh_from_db()
        self.assertGreater(
            self.user.last_activity_at,
            timezone.now() - timedelta(minutes=1),
        )

    def test_activity_is_not_written_on_every_request(self):
        self.go_idle(seconds=10)
        self.user.refresh_from_db()
        recorded = self.user.last_activity_at

        self.client.get(self.me_url)

        self.user.refresh_from_db()
        self.assertEqual(self.user.last_activity_at, recorded)

    def test_logging_in_after_expiry_issues_a_new_token(self):
        self.go_idle(minutes=31)

        new_token = self.login().data["token"]

        self.assertNotEqual(new_token, self.token)
        self.assertFalse(Token.objects.filter(key=self.token).exists())

    def test_logging_in_while_active_keeps_the_token(self):
        self.assertEqual(self.login().data["token"], self.token)

    def test_token_without_recorded_activity_uses_its_creation_time(self):
        self.go_idle(minutes=31)
        User.objects.filter(pk=self.user.pk).update(last_activity_at=None)

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(TOKEN_IDLE_TIMEOUT=timedelta(minutes=5))
    def test_timeout_is_configurable(self):
        self.assertEqual(self.login().data["expires_in"], 300)

        self.go_idle(minutes=6)
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logged_out_token_is_rejected_immediately(self):
        self.client.post("/api/auth/logout/")

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_token_cannot_call_a_protected_endpoint(self):
        self.go_idle(minutes=31)

        response = self.client.get("/api/exams/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
