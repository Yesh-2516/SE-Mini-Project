"""OEP-F-051 / TC-Result-02: class performance report."""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from exam_management.models import Exam
from reports.testing import ReportsWorldMixin, make_user
from accounts.models import User


class ExamReportTests(ReportsWorldMixin, APITestCase):
    def setUp(self):
        self.create_world()
        self.url = f"/api/reports/exams/{self.exam.id}/"
        self.client.force_authenticate(user=self.faculty)

    def test_report_shows_average_highest_and_lowest(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data["summary"]
        self.assertEqual(summary["students_counted"], 4)
        self.assertEqual(summary["average"], Decimal("5.38"))  # 21.5 / 4 = 5.375
        self.assertEqual(summary["highest"], Decimal("10.00"))
        self.assertEqual(summary["lowest"], Decimal("0.00"))
        self.assertEqual(summary["max_score"], 10)

    def test_report_shows_the_score_distribution(self):
        response = self.client.get(self.url)

        distribution = {row["range"]: row["students"] for row in response.data["distribution"]}
        self.assertEqual(len(distribution), 10)
        self.assertEqual(distribution["90-100%"], 1)   # 10 / 10 = 100%
        self.assertEqual(distribution["70-80%"], 1)    # 7.5 / 10 = 75%
        self.assertEqual(distribution["40-50%"], 1)    # 4 / 10 = 40%
        self.assertEqual(distribution["0-10%"], 1)     # 0 / 10 = 0%
        self.assertEqual(sum(distribution.values()), 4)

    def test_bucket_boundaries_lower_inclusive_upper_exclusive(self):
        # 5/10 = 50% belongs to 50-60%, not 40-50%.
        extra = self.add_student("s5", "S005", "Esha", "Pai")
        self.grade(extra, "0", "5", "0")

        response = self.client.get(self.url)

        distribution = {row["range"]: row["students"] for row in response.data["distribution"]}
        self.assertEqual(distribution["50-60%"], 1)
        self.assertEqual(distribution["40-50%"], 1)

    def test_results_list_every_student_best_score_first(self):
        response = self.client.get(self.url)

        results = response.data["results"]
        self.assertEqual([row["roll_number"] for row in results], ["S001", "S002", "S003", "S004"])
        self.assertEqual(results[0]["name"], "Asha Rao")
        self.assertEqual(results[0]["score"], Decimal("10.00"))
        self.assertEqual(results[0]["percentage"], Decimal("100.00"))
        self.assertEqual(results[1]["percentage"], Decimal("75.00"))

    def test_attempts_awaiting_evaluation_are_not_counted(self):
        pending = self.add_student("s5", "S005", "Esha", "Pai")
        self.grade(pending, "2", "0", "0", graded=False)

        response = self.client.get(self.url)

        self.assertEqual(response.data["summary"]["students_counted"], 4)
        self.assertEqual(response.data["summary"]["pending_evaluation"], 1)
        self.assertNotIn("S005", [row["roll_number"] for row in response.data["results"]])

    def test_only_the_latest_graded_attempt_per_student_counts(self):
        self.grade(self.s2, "2", "5", "2", started_minutes_ago=5)  # re-attempt: 9

        response = self.client.get(self.url)

        self.assertEqual(response.data["summary"]["students_counted"], 4)
        row = next(r for r in response.data["results"] if r["roll_number"] == "S002")
        self.assertEqual(row["score"], Decimal("9.00"))

    def test_exam_without_graded_results_has_an_empty_report(self):
        empty = Exam.objects.create(title="Empty Exam", duration_minutes=30)

        response = self.client.get(f"/api/reports/exams/{empty.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        summary = response.data["summary"]
        self.assertEqual(summary["students_counted"], 0)
        self.assertIsNone(summary["average"])
        self.assertIsNone(summary["highest"])
        self.assertIsNone(summary["lowest"])
        self.assertEqual(sum(row["students"] for row in response.data["distribution"]), 0)
        self.assertEqual(response.data["results"], [])

    def test_scores_of_other_exams_are_not_mixed_in(self):
        other = Exam.objects.create(title="Other Exam", duration_minutes=30)
        response = self.client.get(f"/api/reports/exams/{other.id}/")

        self.assertEqual(response.data["summary"]["students_counted"], 0)

    def test_unknown_exam_returns_404(self):
        response = self.client.get("/api/reports/exams/999999/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_view_the_report(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_student_cannot_view_the_report(self):
        self.client.force_authenticate(user=self.s1)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_view_the_report(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_faculty_cannot_view_the_report(self):
        inactive = make_user("rep_inactive", User.Role.FACULTY, is_active=False)
        self.client.force_authenticate(user=inactive)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
