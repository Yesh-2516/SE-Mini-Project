import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db import connection
from django.test import RequestFactory, TestCase
from django.views.debug import SafeExceptionReporterFilter
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.views import StudentRegistrationView

User = get_user_model()

PASSWORD = "Pl@intext-Never-Stored-42"


class _CollectingHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(self.format(record))


class PasswordHashingTests(APITestCase):
    """TC-Sec-02: passwords are stored only as Argon2 hashes."""

    def register(self, **overrides):
        data = {
            "first_name": "Ravi",
            "email": "ravi@college.edu",
            "roll_number": "CS200",
            "password": PASSWORD,
        }
        data.update(overrides)
        return self.client.post("/api/auth/register/", data, format="json")

    def test_default_hasher_is_argon2(self):
        encoded = make_password(PASSWORD)

        self.assertEqual(identify_hasher(encoded).algorithm, "argon2")
        self.assertTrue(check_password(PASSWORD, encoded))

    def test_registered_password_is_stored_as_argon2_hash(self):
        response = self.register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(pk=response.data["id"])

        self.assertTrue(user.password.startswith("argon2$"))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_no_plaintext_password_in_database_row(self):
        response = self.register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        table = connection.ops.quote_name(User._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()

        for row in rows:
            for value in row:
                self.assertNotIn(PASSWORD, str(value))

    def test_legacy_pbkdf2_hash_is_upgraded_on_password_check(self):
        user = User.objects.create_user(username="legacy")
        user.password = make_password(PASSWORD, hasher="pbkdf2_sha256")
        user.save()

        self.assertTrue(user.check_password(PASSWORD))
        user.refresh_from_db()

        self.assertTrue(user.password.startswith("argon2$"))

    def test_no_plaintext_password_in_logs(self):
        handler = _CollectingHandler()
        root = logging.getLogger()
        previous_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)

        try:
            self.register()
            # Duplicate and policy failures exercise the error paths too.
            self.register()
            self.register(email="x@college.edu", roll_number="CS201", password="Zq9!xW")
        finally:
            root.removeHandler(handler)
            root.setLevel(previous_level)

        for message in handler.messages:
            self.assertNotIn(PASSWORD, message)
            self.assertNotIn("Zq9!xW", message)


class SensitiveParameterTests(TestCase):
    def test_registration_password_is_masked_in_error_reports(self):
        request = RequestFactory().post(
            "/api/auth/register/",
            {"first_name": "Ravi", "email": "ravi@college.edu", "password": PASSWORD},
        )

        StudentRegistrationView.as_view()(request)

        cleansed = SafeExceptionReporterFilter().get_post_parameters(request)
        self.assertNotEqual(cleansed["password"], PASSWORD)
        self.assertEqual(cleansed["email"], "ravi@college.edu")
