from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = "Str0ng-Passphrase!"
LIST_URL = "/api/admin/users/"


def detail_url(user_id):
    return f"{LIST_URL}{user_id}/"


class AccountManagementTests(APITestCase):
    """TC-Admin-01: admin creates, edits and deactivates accounts."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="portal_admin",
            password=PASSWORD,
            role=User.Role.ADMIN,
        )
        self.faculty = User.objects.create_user(
            username="prof.iyer",
            email="iyer@college.edu",
            password=PASSWORD,
            role=User.Role.FACULTY,
        )
        self.student = User.objects.create_user(
            username="cs400",
            email="neha@college.edu",
            roll_number="CS400",
            password=PASSWORD,
            role=User.Role.STUDENT,
        )
        self.client.force_authenticate(user=self.admin)

    def account_data(self, **overrides):
        data = {
            "first_name": "Sunil",
            "last_name": "Kumar",
            "email": "sunil@college.edu",
            "role": "FACULTY",
            "password": PASSWORD,
        }
        data.update(overrides)
        return data

    # Create

    def test_admin_creates_faculty_account(self):
        response = self.client.post(LIST_URL, self.account_data(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], "FACULTY")
        self.assertEqual(response.data["username"], "sunil@college.edu")
        self.assertTrue(response.data["is_active"])
        self.assertNotIn("password", response.data)

        user = User.objects.get(pk=response.data["id"])
        self.assertTrue(user.check_password(PASSWORD))
        self.assertTrue(user.password.startswith("argon2$"))

    def test_admin_creates_student_account_with_roll_number(self):
        response = self.client.post(
            LIST_URL,
            self.account_data(email="", roll_number="cs401", role="STUDENT"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["role"], "STUDENT")
        self.assertEqual(response.data["roll_number"], "CS401")
        self.assertEqual(response.data["username"], "cs401")

    def test_admin_can_set_explicit_username(self):
        response = self.client.post(
            LIST_URL,
            self.account_data(username="prof.kumar"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["username"], "prof.kumar")

    def test_created_account_can_log_in(self):
        self.client.post(LIST_URL, self.account_data(), format="json")
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/auth/login/",
            {"email": "sunil@college.edu", "password": PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "FACULTY")

    def test_admin_cannot_create_admin_accounts(self):
        response = self.client.post(
            LIST_URL,
            self.account_data(role="ADMIN"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

    def test_create_requires_password(self):
        data = self.account_data()
        del data["password"]

        response = self.client.post(LIST_URL, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_create_rejects_weak_password(self):
        response = self.client.post(
            LIST_URL,
            self.account_data(password="12345678"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    def test_create_rejects_duplicate_email(self):
        response = self.client.post(
            LIST_URL,
            self.account_data(email="IYER@college.edu"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("email", response.data)

    def test_create_rejects_duplicate_username(self):
        response = self.client.post(
            LIST_URL,
            self.account_data(username="prof.iyer"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("username", response.data)

    # List and retrieve

    def test_list_excludes_admin_accounts(self):
        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {account["id"] for account in response.data}
        self.assertEqual(ids, {self.faculty.id, self.student.id})

    def test_list_filters_by_role(self):
        response = self.client.get(LIST_URL, {"role": "student"})

        self.assertEqual(
            [account["id"] for account in response.data],
            [self.student.id],
        )

    def test_list_filters_by_active_state(self):
        self.client.post(f"{detail_url(self.student.id)}deactivate/")

        response = self.client.get(LIST_URL, {"is_active": "false"})

        self.assertEqual(
            [account["id"] for account in response.data],
            [self.student.id],
        )

    def test_admin_accounts_cannot_be_retrieved(self):
        response = self.client.get(detail_url(self.admin.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # Edit

    def test_admin_edits_account_details(self):
        response = self.client.patch(
            detail_url(self.faculty.id),
            {"first_name": "Lakshmi", "email": "l.iyer@college.edu"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.first_name, "Lakshmi")
        self.assertEqual(self.faculty.email, "l.iyer@college.edu")
        self.assertTrue(self.faculty.check_password(PASSWORD))

    def test_admin_changes_role_between_faculty_and_student(self):
        response = self.client.patch(
            detail_url(self.student.id),
            {"role": "FACULTY"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, User.Role.FACULTY)

    def test_edit_cannot_promote_to_admin(self):
        response = self.client.patch(
            detail_url(self.faculty.id),
            {"role": "ADMIN"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.faculty.refresh_from_db()
        self.assertEqual(self.faculty.role, User.Role.FACULTY)

    def test_edit_keeping_own_email_is_not_a_duplicate(self):
        response = self.client.patch(
            detail_url(self.faculty.id),
            {"email": "iyer@college.edu", "last_name": "Iyer"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_edit_rejects_email_of_another_account(self):
        response = self.client.patch(
            detail_url(self.faculty.id),
            {"email": "neha@college.edu"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_edit_cannot_remove_both_email_and_roll_number(self):
        response = self.client.patch(
            detail_url(self.faculty.id),
            {"email": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_reset_signs_user_out(self):
        Token.objects.create(user=self.faculty)

        response = self.client.patch(
            detail_url(self.faculty.id),
            {"password": "An0ther-Passphrase!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.faculty.refresh_from_db()
        self.assertTrue(self.faculty.check_password("An0ther-Passphrase!"))
        self.assertFalse(Token.objects.filter(user=self.faculty).exists())

    def test_is_active_cannot_be_changed_through_edit(self):
        self.client.patch(
            detail_url(self.faculty.id),
            {"is_active": False},
            format="json",
        )

        self.faculty.refresh_from_db()
        self.assertTrue(self.faculty.is_active)

    # Deactivate

    def test_deactivated_account_cannot_log_in(self):
        response = self.client.post(f"{detail_url(self.faculty.id)}deactivate/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_active"])

        self.client.force_authenticate(user=None)
        login = self.client.post(
            "/api/auth/login/",
            {"username": "prof.iyer", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_deactivation_revokes_existing_token(self):
        token = Token.objects.create(user=self.faculty)

        self.client.post(f"{detail_url(self.faculty.id)}deactivate/")

        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reactivated_account_can_log_in_again(self):
        self.client.post(f"{detail_url(self.faculty.id)}deactivate/")
        response = self.client.post(f"{detail_url(self.faculty.id)}activate/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_active"])

        self.client.force_authenticate(user=None)
        login = self.client.post(
            "/api/auth/login/",
            {"username": "prof.iyer", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_admin_accounts_cannot_be_deactivated_here(self):
        response = self.client.post(f"{detail_url(self.admin.id)}deactivate/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    # Access control

    def test_faculty_and_students_cannot_manage_accounts(self):
        for user in (self.faculty, self.student):
            self.client.force_authenticate(user=user)
            with self.subTest(role=user.role):
                listing = self.client.get(LIST_URL)
                create = self.client.post(LIST_URL, self.account_data(), format="json")
                deactivate = self.client.post(f"{detail_url(self.student.id)}deactivate/")

                for response in (listing, create, deactivate):
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)
