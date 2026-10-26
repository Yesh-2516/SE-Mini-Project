from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

VALID_PASSWORD = "Str0ng-Passphrase!"


class UserModelTests(TestCase):
    def test_new_users_default_to_student_role(self):
        user = User.objects.create_user(username="someone", password=VALID_PASSWORD)

        self.assertEqual(user.role, User.Role.STUDENT)

    def test_superuser_gets_admin_role(self):
        user = User.objects.create_superuser(
            username="root",
            email="root@college.edu",
            password=VALID_PASSWORD,
        )

        self.assertEqual(user.role, User.Role.ADMIN)

    def test_email_and_roll_number_are_normalized(self):
        user = User.objects.create_user(
            username="normalized",
            email="  Student@College.EDU ",
            roll_number=" cs820 ",
            password=VALID_PASSWORD,
        )

        self.assertEqual(user.email, "student@college.edu")
        self.assertEqual(user.roll_number, "CS820")

    def test_blank_email_and_roll_number_are_stored_as_null(self):
        first = User.objects.create_user(username="first", password=VALID_PASSWORD)
        second = User.objects.create_user(username="second", password=VALID_PASSWORD)

        self.assertIsNone(first.email)
        self.assertIsNone(second.roll_number)


class StudentRegistrationTests(APITestCase):
    """TC-Auth-01: student self-registration."""

    url = "/api/auth/register/"

    def registration_data(self, **overrides):
        data = {
            "first_name": "Asha",
            "last_name": "Rao",
            "email": "asha.rao@college.edu",
            "roll_number": "CS101",
            "password": VALID_PASSWORD,
        }
        data.update(overrides)
        return data

    def test_register_with_email_and_roll_number(self):
        response = self.client.post(self.url, self.registration_data(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "asha.rao@college.edu")
        self.assertEqual(response.data["roll_number"], "CS101")
        self.assertEqual(response.data["role"], User.Role.STUDENT)
        self.assertNotIn("password", response.data)

        user = User.objects.get(pk=response.data["id"])
        self.assertTrue(user.check_password(VALID_PASSWORD))
        self.assertTrue(user.is_active)

    def test_register_with_email_only(self):
        response = self.client.post(
            self.url,
            self.registration_data(roll_number=""),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["username"], "asha.rao@college.edu")
        self.assertIsNone(response.data["roll_number"])

    def test_register_with_roll_number_only(self):
        data = self.registration_data()
        del data["email"]

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["username"], "cs101")
        self.assertIsNone(response.data["email"])

    def test_register_requires_email_or_roll_number(self):
        response = self.client.post(
            self.url,
            self.registration_data(email="", roll_number=""),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.count(), 0)

    def test_register_rejects_invalid_email(self):
        response = self.client.post(
            self.url,
            self.registration_data(email="not-an-email"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_role_in_request_is_ignored(self):
        response = self.client.post(
            self.url,
            self.registration_data(role="ADMIN"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(pk=response.data["id"])
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_duplicate_email_is_rejected(self):
        self.client.post(self.url, self.registration_data(), format="json")

        response = self.client.post(
            self.url,
            self.registration_data(email="ASHA.RAO@college.edu", roll_number="CS102"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_roll_number_is_rejected(self):
        self.client.post(self.url, self.registration_data(), format="json")

        response = self.client.post(
            self.url,
            self.registration_data(email="other@college.edu", roll_number="cs101"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("roll_number", response.data)
        self.assertEqual(User.objects.count(), 1)

    def test_short_password_violates_policy(self):
        response = self.client.post(
            self.url,
            self.registration_data(password="Ab1!"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
        self.assertIn("password", response.data)
        self.assertEqual(User.objects.count(), 0)

    def test_common_password_violates_policy(self):
        response = self.client.post(
            self.url,
            self.registration_data(password="password123"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    def test_numeric_password_violates_policy(self):
        response = self.client.post(
            self.url,
            self.registration_data(password="8203947561"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    def test_password_similar_to_email_violates_policy(self):
        response = self.client.post(
            self.url,
            self.registration_data(password="asha.rao.college"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    def test_missing_password_is_bad_request(self):
        data = self.registration_data()
        del data["password"]

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
