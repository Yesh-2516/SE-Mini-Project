"""OEP-F-042 / TC-Eval-03: marks and feedback on subjective answers."""

from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from evaluation.testing import EvaluationWorldMixin
from exam_delivery.models import Attempt


class EvaluateResponseTests(EvaluationWorldMixin, APITestCase):
    def setUp(self):
        self.create_world()
        self.attempt = self.make_attempt(self.student)
        self.short_a_response = self.response_for(self.attempt, self.short_a)
        self.short_b_response = self.response_for(self.attempt, self.short_b)
        self.client.force_authenticate(user=self.faculty)

    def grade(self, response, payload):
        return self.client.patch(self.grade_url(response), payload, format="json")

    def test_faculty_can_award_marks_and_feedback(self):
        result = self.grade(
            self.short_a_response,
            {"marks": "4.50", "feedback": "Good, but give an example."},
        )

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        self.short_a_response.refresh_from_db()
        self.assertEqual(self.short_a_response.marks_obtained, Decimal("4.50"))
        self.assertEqual(
            self.short_a_response.feedback, "Good, but give an example."
        )
        self.assertEqual(self.short_a_response.evaluated_by, self.faculty)
        self.assertIsNotNone(self.short_a_response.evaluated_at)

    def test_marks_up_to_the_maximum_are_accepted(self):
        result = self.grade(self.short_a_response, {"marks": "5"})

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        self.assertEqual(result.data["max_marks"], 5)

    def test_zero_marks_are_accepted(self):
        result = self.grade(self.short_a_response, {"marks": "0"})

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        self.short_a_response.refresh_from_db()
        self.assertEqual(self.short_a_response.marks_obtained, Decimal("0.00"))
        self.assertIsNotNone(self.short_a_response.evaluated_at)

    def test_marks_above_the_maximum_are_rejected(self):
        result = self.grade(self.short_a_response, {"marks": "5.01"})

        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("marks", result.data)
        self.short_a_response.refresh_from_db()
        self.assertIsNone(self.short_a_response.marks_obtained)
        self.assertIsNone(self.short_a_response.evaluated_at)

    def test_maximum_is_the_marks_of_that_question_in_the_exam(self):
        result = self.grade(self.short_b_response, {"marks": "4"})

        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_marks_are_rejected(self):
        result = self.grade(self.short_a_response, {"marks": "-1"})

        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)
        self.short_a_response.refresh_from_db()
        self.assertIsNone(self.short_a_response.marks_obtained)

    def test_marks_must_be_a_number(self):
        for bad in ("abc", "", None, "NaN"):
            with self.subTest(marks=bad):
                result = self.grade(self.short_a_response, {"marks": bad})
                self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)

    def test_marks_are_required(self):
        result = self.grade(self.short_a_response, {"feedback": "No marks given"})

        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("marks", result.data)

    def test_more_than_two_decimal_places_are_rejected(self):
        result = self.grade(self.short_a_response, {"marks": "2.555"})

        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)

    def test_objective_responses_cannot_be_evaluated_manually(self):
        mcq_response = self.response_for(self.attempt, self.mcq)

        result = self.grade(mcq_response, {"marks": "1"})

        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)
        mcq_response.refresh_from_db()
        self.assertEqual(mcq_response.marks_obtained, Decimal("2.00"))
        self.assertIsNone(mcq_response.evaluated_by)

    def test_responses_of_unsubmitted_attempts_cannot_be_evaluated(self):
        in_progress = self.make_attempt(
            self.other_student, status=Attempt.Status.IN_PROGRESS
        )
        response = self.response_for(in_progress, self.short_a)

        result = self.grade(response, {"marks": "3"})

        self.assertEqual(result.status_code, status.HTTP_409_CONFLICT)
        response.refresh_from_db()
        self.assertIsNone(response.marks_obtained)

    def test_unknown_response_returns_404(self):
        result = self.client.patch(
            "/api/evaluation/responses/999999/", {"marks": "1"}, format="json"
        )

        self.assertEqual(result.status_code, status.HTTP_404_NOT_FOUND)

    def test_omitting_feedback_keeps_existing_feedback(self):
        self.grade(self.short_a_response, {"marks": "3", "feedback": "First pass"})

        self.grade(self.short_a_response, {"marks": "4"})

        self.short_a_response.refresh_from_db()
        self.assertEqual(self.short_a_response.feedback, "First pass")
        self.assertEqual(self.short_a_response.marks_obtained, Decimal("4.00"))

    def test_empty_feedback_clears_it(self):
        self.grade(self.short_a_response, {"marks": "3", "feedback": "First pass"})

        self.grade(self.short_a_response, {"marks": "3", "feedback": ""})

        self.short_a_response.refresh_from_db()
        self.assertEqual(self.short_a_response.feedback, "")

    def test_admin_can_evaluate_too(self):
        self.client.force_authenticate(user=self.admin)

        result = self.grade(self.short_a_response, {"marks": "2"})

        self.assertEqual(result.status_code, status.HTTP_200_OK)
        self.short_a_response.refresh_from_db()
        self.assertEqual(self.short_a_response.evaluated_by, self.admin)

    def test_student_cannot_evaluate(self):
        self.client.force_authenticate(user=self.student)

        result = self.grade(self.short_a_response, {"marks": "5"})

        self.assertEqual(result.status_code, status.HTTP_403_FORBIDDEN)
        self.short_a_response.refresh_from_db()
        self.assertIsNone(self.short_a_response.marks_obtained)

    def test_anonymous_cannot_evaluate(self):
        self.client.force_authenticate(user=None)

        result = self.grade(self.short_a_response, {"marks": "5"})

        self.assertEqual(result.status_code, status.HTTP_401_UNAUTHORIZED)


class FinalScoreIntegrationTests(EvaluationWorldMixin, APITestCase):
    """F-042 calls finalize_attempt_score (F-043) in the same request."""

    def setUp(self):
        self.create_world()
        self.attempt = self.make_attempt(self.student)
        self.short_a_response = self.response_for(self.attempt, self.short_a)
        self.short_b_response = self.response_for(self.attempt, self.short_b)
        self.client.force_authenticate(user=self.faculty)

    def grade(self, response, marks):
        return self.client.patch(
            self.grade_url(response), {"marks": marks}, format="json"
        )

    def test_attempt_is_not_final_until_every_answer_is_evaluated(self):
        result = self.grade(self.short_a_response, "4")

        self.assertFalse(result.data["attempt"]["finalized"])
        self.assertEqual(result.data["attempt"]["pending_count"], 1)
        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.is_graded)
        self.assertEqual(self.attempt.total_score, Decimal("0.00"))

    def test_last_evaluation_finalizes_the_attempt(self):
        self.grade(self.short_a_response, "4.50")

        result = self.grade(self.short_b_response, "3")

        self.assertTrue(result.data["attempt"]["finalized"])
        self.assertEqual(result.data["attempt"]["pending_count"], 0)
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_graded)
        self.assertEqual(self.attempt.objective_score, Decimal("2.00"))
        self.assertEqual(self.attempt.subjective_score, Decimal("7.50"))
        self.assertEqual(self.attempt.total_score, Decimal("9.50"))

    def test_regrading_recalculates_the_total(self):
        self.grade(self.short_a_response, "4.50")
        self.grade(self.short_b_response, "3")

        result = self.grade(self.short_a_response, "1")

        self.assertTrue(result.data["regraded"])
        self.assertTrue(result.data["attempt"]["finalized"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.subjective_score, Decimal("4.00"))
        self.assertEqual(self.attempt.total_score, Decimal("6.00"))
        self.assertTrue(self.attempt.is_graded)

    def test_first_evaluation_is_not_reported_as_a_regrade(self):
        result = self.grade(self.short_a_response, "4")

        self.assertFalse(result.data["regraded"])
