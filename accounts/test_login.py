from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = "Str0ng-Passphrase!"


class LoginTests(APITestCase):
    """TC-Auth-02: users log in with username, email or roll number."""

    url = "/api/auth/login/"

    def setUp(self):
        self.student = User.objects.create_user(
            username="meera",
            email="meera@college.edu",
            roll_number="CS300",
            password=PASSWORD,
            role=User.Role.STUDENT,
        )
        self.faculty = User.objects.create_user(
            username="prof.iyer",
            email="iyer@college.edu",
            password=PASSWORD,
            role=User.Role.FACULTY,
        )

    def login(self, **data):
        return self.client.post(self.url, data, format="json")

    def test_login_with_username_returns_token_and_role(self):
        response = self.login(username="prof.iyer", password=PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], User.Role.FACULTY)
        self.assertEqual(response.data["user"]["id"], self.faculty.id)
        self.assertEqual(
            response.data["token"],
            Token.objects.get(user=self.faculty).key,
        )

    def test_login_with_email_is_case_insensitive(self):
        response = self.login(email="Meera@College.edu", password=PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], User.Role.STUDENT)

    def test_login_with_roll_number(self):
        response = self.login(username="cs300", password=PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], self.student.id)

    def test_login_records_last_login(self):
        self.login(username="prof.iyer", password=PASSWORD)

        self.faculty.refresh_from_db()
        self.assertIsNotNone(self.faculty.last_login)

    def test_wrong_password_is_rejected(self):
        response = self.login(username="prof.iyer", password="Wrong-Passphrase!")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("token", response.data)
        self.assertFalse(Token.objects.filter(user=self.faculty).exists())

    def test_unknown_user_is_rejected_with_same_error(self):
        unknown = self.login(username="nobody", password=PASSWORD)
        wrong = self.login(username="prof.iyer", password="Wrong-Passphrase!")

        self.assertEqual(unknown.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(unknown.data, wrong.data)

    def test_plaintext_password_in_database_does_not_log_in(self):
        # The password is checked against the stored hash, never compared raw.
        User.objects.filter(pk=self.faculty.pk).update(password=PASSWORD)

        response = self.login(username="prof.iyer", password=PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_cannot_log_in(self):
        self.faculty.is_active = False
        self.faculty.save()

        response = self.login(username="prof.iyer", password=PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_identifier_is_bad_request(self):
        response = self.login(password=PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registered_student_can_log_in(self):
        self.client.post(
            "/api/auth/register/",
            {
                "first_name": "Kiran",
                "email": "kiran@college.edu",
                "password": PASSWORD,
            },
            format="json",
        )

        response = self.login(email="kiran@college.edu", password=PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], User.Role.STUDENT)


class TokenSessionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="prof.iyer",
            password=PASSWORD,
            role=User.Role.FACULTY,
        )
        response = self.client.post(
            "/api/auth/login/",
            {"username": "prof.iyer", "password": PASSWORD},
            format="json",
        )
        self.token = response.data["token"]

    def test_token_authenticates_current_user_endpoint(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "prof.iyer")
        self.assertEqual(response.data["role"], User.Role.FACULTY)

    def test_current_user_requires_authentication(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalidates_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        logout = self.client.post("/api/auth/logout/")
        after = self.client.get("/api/auth/me/")

        self.assertEqual(logout.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(after.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
