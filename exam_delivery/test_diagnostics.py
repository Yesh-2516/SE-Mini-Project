from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AdminDiagnosticsTests(APITestCase):
    """TC-Admin-04: Admin health diagnostics panel (OEP-F-063)."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin_diagnostics",
            email="admin_diag@institution.edu",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
        )
        self.faculty = User.objects.create_user(
            username="faculty_diagnostics",
            email="faculty_diag@institution.edu",
            password="StrongPassword123!",
            role=User.Role.FACULTY,
        )
        self.student = User.objects.create_user(
            username="student_diagnostics",
            email="student_diag@institution.edu",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
        )
        self.url = "/api/admin/diagnostics/"

    def test_admin_can_access_health_diagnostics_panel(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        self.assertEqual(data["status"], "healthy")
        self.assertIn("timestamp", data)

        # Server metrics
        self.assertIn("server", data)
        self.assertEqual(data["server"]["status"], "operational")
        self.assertIn("python_version", data["server"])
        self.assertIn("django_version", data["server"])

        # Database health
        self.assertIn("database", data)
        self.assertEqual(data["database"]["status"], "connected")
        self.assertIsNotNone(data["database"]["latency_ms"])

        # Metric counts
        self.assertIn("metrics", data)
        self.assertIn("active_attempts", data["metrics"])
        self.assertIn("total_exams", data["metrics"])
        self.assertIn("total_users", data["metrics"])

    def test_faculty_cannot_access_diagnostics_panel(self):
        self.client.force_authenticate(user=self.faculty)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_access_diagnostics_panel(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_user_cannot_access_diagnostics_panel(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
