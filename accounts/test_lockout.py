from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.audit_models import AuditLog

User = get_user_model()

PASSWORD = "Str0ng-Passphrase!"
WRONG_PASSWORD = "Wrong-Passphrase!"


class LockoutTestCase(APITestCase):
    url = "/api/auth/login/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="meera",
            email="meera@college.edu",
            roll_number="CS300",
            password=PASSWORD,
            role=User.Role.STUDENT,
        )

    def login(self, password=PASSWORD, username="meera"):
        return self.client.post(
            self.url,
            {"username": username, "password": password},
            format="json",
        )

    def fail_logins(self, count):
        return [self.login(WRONG_PASSWORD) for _ in range(count)]

    def expire_lock(self):
        User.objects.filter(pk=self.user.pk).update(
            locked_until=timezone.now() - timedelta(seconds=1)
        )


class AccountLockoutTests(LockoutTestCase):
    """TC-Auth-04: five failed logins in a row lock the account."""

    def test_four_failures_do_not_lock(self):
        responses = self.fail_logins(4)

        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.login().status_code, status.HTTP_200_OK)

    def test_fifth_consecutive_failure_locks_the_account(self):
        response = self.fail_logins(5)[-1]

        self.assertEqual(response.status_code, status.HTTP_423_LOCKED)
        self.user.refresh_from_db()
        self.assertGreater(self.user.locked_until, timezone.now())

    def test_correct_password_is_refused_while_locked(self):
        self.fail_logins(5)

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_423_LOCKED)
        self.assertNotIn("token", response.data)

    def test_login_works_again_after_the_lock_expires(self):
        self.fail_logins(5)
        self.expire_lock()

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.locked_until)

    def test_counter_starts_again_after_the_lock_expires(self):
        self.fail_logins(5)
        self.expire_lock()

        response = self.fail_logins(1)[0]

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_successful_login_resets_the_count(self):
        self.fail_logins(4)
        self.login()

        response = self.fail_logins(4)[-1]

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.locked_until)

    def test_failures_count_across_every_identifier(self):
        for username in ("meera", "meera@college.edu", "cs300", "CS300", "meera"):
            response = self.login(WRONG_PASSWORD, username=username)

        self.assertEqual(response.status_code, status.HTTP_423_LOCKED)

    def test_attempts_while_locked_do_not_extend_the_lock(self):
        self.fail_logins(5)
        self.user.refresh_from_db()
        locked_until = self.user.locked_until

        self.fail_logins(3)

        self.user.refresh_from_db()
        self.assertEqual(self.user.locked_until, locked_until)

    def test_unknown_account_is_never_reported_as_locked(self):
        for _ in range(6):
            response = self.login(WRONG_PASSWORD, username="nobody")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_failed_logins_on_inactive_account_are_not_counted(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        self.fail_logins(5)

        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertIsNone(self.user.locked_until)

    def test_lock_also_applies_outside_the_login_endpoint(self):
        # The Django admin site logs in through the same backend.
        self.fail_logins(5)

        self.assertIsNone(authenticate(username="meera", password=PASSWORD))

    @override_settings(
        ACCOUNT_LOCKOUT_THRESHOLD=2,
        ACCOUNT_LOCKOUT_DURATION=timedelta(minutes=1),
    )
    def test_threshold_and_duration_are_configurable(self):
        response = self.fail_logins(2)[-1]

        self.assertEqual(response.status_code, status.HTTP_423_LOCKED)
        self.user.refresh_from_db()
        self.assertLessEqual(
            self.user.locked_until,
            timezone.now() + timedelta(minutes=1),
        )


class LockoutAuditTests(LockoutTestCase):
    """TC-Sec-05: each lockout creates an audit-log entry."""

    def lockout_entries(self):
        return AuditLog.objects.filter(event_type="account.locked")

    def test_lockout_records_account_and_timestamp(self):
        before = timezone.now()

        self.fail_logins(5)

        entry = self.lockout_entries().get()
        self.assertEqual(entry.actor, self.user)
        self.assertEqual(entry.metadata["target_user_id"], self.user.pk)
        self.assertGreaterEqual(entry.created_at, before)
        self.assertEqual(entry.ip_address, "127.0.0.1")

    def test_no_entry_before_the_threshold(self):
        self.fail_logins(4)

        self.assertFalse(self.lockout_entries().exists())

    def test_each_lockout_creates_one_entry(self):
        self.fail_logins(7)
        self.assertEqual(self.lockout_entries().count(), 1)

        self.expire_lock()
        self.fail_logins(5)

        self.assertEqual(self.lockout_entries().count(), 2)

    def test_entry_does_not_contain_the_attempted_password(self):
        self.fail_logins(5)

        entry = self.lockout_entries().get()
        self.assertNotIn(WRONG_PASSWORD, f"{entry.description}{entry.metadata}")
