"""OEP-F-053 / TC-Result-04: question-wise breakdown."""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from exam_management.models import Exam
from reports.testing import ReportsWorldMixin


class QuestionBreakdownTests(ReportsWorldMixin, APITestCase):
    def setUp(self):
        self.create_world()
        self.url = f"/api/reports/exams/{self.exam.id}/questions/"
        self.client.force_authenticate(user=self.faculty)

    def by_question(self, response):
        return {row["question_id"]: row for row in response.data["questions"]}

    def test_each_question_shows_the_percentage_who_got_it_right(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = self.by_question(response)
        # Full marks: MCQ -> s1, s2; short A -> s1; short B -> s1.
        self.assertEqual(rows[self.mcq.id]["percent_correct"], Decimal("50.00"))
        self.assertEqual(rows[self.short_a.id]["percent_correct"], Decimal("25.00"))
        self.assertEqual(rows[self.short_b.id]["percent_correct"], Decimal("25.00"))
        self.assertEqual(rows[self.mcq.id]["correct_count"], 2)
        self.assertEqual(rows[self.mcq.id]["students"], 4)

    def test_average_marks_show_partial_credit(self):
        rows = self.by_question(self.client.get(self.url))

        self.assertEqual(rows[self.mcq.id]["average_marks"], Decimal("1.00"))
        self.assertEqual(rows[self.short_a.id]["average_marks"], Decimal("2.88"))  # 11.5 / 4
        self.assertEqual(rows[self.short_b.id]["average_marks"], Decimal("1.50"))

    def test_unanswered_questions_are_visible(self):
        rows = self.by_question(self.client.get(self.url))

        self.assertEqual(rows[self.short_a.id]["answered_count"], 3)  # s4 left it blank

    def test_questions_are_listed_in_exam_order_with_their_marks(self):
        response = self.client.get(self.url)

        self.assertEqual([q["position"] for q in response.data["questions"]], [1, 2, 3])
        self.assertEqual([q["max_marks"] for q in response.data["questions"]], [2, 5, 3])

    def test_breakdown_is_per_exam(self):
        other = Exam.objects.create(title="Other Exam", duration_minutes=30)

        response = self.client.get(f"/api/reports/exams/{other.id}/questions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["students_counted"], 0)
        self.assertEqual(response.data["questions"], [])

    def test_ungraded_attempts_do_not_count(self):
        pending = self.add_student("s5", "S005", "Esha", "Pai")
        self.grade(pending, "2", "5", "3", graded=False)

        response = self.client.get(self.url)

        self.assertEqual(response.data["students_counted"], 4)
        rows = self.by_question(response)
        self.assertEqual(rows[self.mcq.id]["percent_correct"], Decimal("50.00"))

    def test_without_graded_results_percentages_are_empty(self):
        from exam_management.models import ExamQuestion
        empty = Exam.objects.create(title="Empty Exam", duration_minutes=30)
        ExamQuestion.objects.create(exam=empty, question=self.mcq, position=1, marks=2)

        response = self.client.get(f"/api/reports/exams/{empty.id}/questions/")

        row = response.data["questions"][0]
        self.assertIsNone(row["percent_correct"])
        self.assertIsNone(row["average_marks"])

    def test_answer_keys_are_not_exposed(self):
        response = self.client.get(self.url)

        self.assertNotIn("correct_answer", str(response.data))

    def test_unknown_exam_returns_404(self):
        response = self.client.get("/api/reports/exams/999999/questions/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_breakdown_is_restricted_to_faculty(self):
        for user, expected in (
            (self.admin, status.HTTP_403_FORBIDDEN),
            (self.s1, status.HTTP_403_FORBIDDEN),
            (None, status.HTTP_401_UNAUTHORIZED),
        ):
            with self.subTest(user=getattr(user, "role", "anonymous")):
                self.client.force_authenticate(user=user)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, expected)
