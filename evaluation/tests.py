from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course
from exam_delivery.models import Attempt, Response
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question
from evaluation.services import finalize_attempt_score


User = get_user_model()


class ObjectiveGradingCloseOutTests(APITestCase):
    def setUp(self):
        self.now = timezone.now()

        self.student = User.objects.create_user(
            username="evaluation_student",
            email="evaluation_student@example.com",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
        )

        self.exam = Exam.objects.create(
            title="Objective Grading Close-Out",
            duration_minutes=30,
            availability_start=self.now - timedelta(minutes=5),
            availability_end=self.now + timedelta(hours=1),
            negative_marking_enabled=True,
            negative_marks=Decimal("0.50"),
        )

        # OEP-F-024: students may sit only published exams assigned to their courses.
        course = Course.objects.create(code="OBJ101", name="Objective Grading Course")
        course.students.add(self.student)
        self.exam.courses.add(course)
        self.exam.status = Exam.Status.PUBLISHED
        self.exam.save(update_fields=["status"])

        self.question = Question.objects.create(
            text="What does CPU stand for?",
            question_type=Question.QuestionType.MCQ,
            options=["Central Processing Unit", "Computer Personal Unit"],
            correct_answer="Central Processing Unit",
            subject="Computer Science",
            topic="Computer Architecture",
            difficulty=Question.Difficulty.EASY,
        )

        ExamQuestion.objects.create(
            exam=self.exam,
            question=self.question,
            position=1,
            marks=2,
        )

    def test_blank_objective_answer_receives_zero_on_submission(self):
        self.client.force_authenticate(user=self.student)

        start_response = self.client.post(
            f"/api/exams/{self.exam.id}/start/"
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)

        attempt_id = start_response.data["attempt_id"]

        submit_response = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/",
            {
                "reason": "manual",
                "responses": [
                    {
                        "question_id": self.question.id,
                        "submitted_answer": "",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(submit_response.status_code, status.HTTP_200_OK)

        attempt = Attempt.objects.get(pk=attempt_id)
        response = Response.objects.get(
            attempt=attempt,
            question=self.question,
        )

        self.assertEqual(response.marks_obtained, Decimal("0"))
        self.assertEqual(attempt.objective_score, Decimal("0.00"))
        self.assertTrue(attempt.is_graded)
        self.assertEqual(attempt.total_score, Decimal("0.00"))


class FinalizeAttemptScoreTests(APITestCase):
    def setUp(self):
        self.now = timezone.now()

        self.student = User.objects.create_user(
            username="final_score_student",
            email="final_score_student@example.com",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
        )

        self.exam = Exam.objects.create(
            title="Final Score Test",
            duration_minutes=30,
        )

        self.attempt = Attempt.objects.create(
            exam=self.exam,
            student=self.student,
            status=Attempt.Status.SUBMITTED,
            ends_at=self.now + timedelta(minutes=30),
            objective_score=Decimal("3.00"),
        )

        self.subjective_question = Question.objects.create(
            text="Explain normalization.",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="",
            subject="Computer Science",
            topic="DBMS",
            difficulty=Question.Difficulty.EASY,
        )

        ExamQuestion.objects.create(
            exam=self.exam,
            question=self.subjective_question,
            position=1,
            marks=5,
        )

    def create_subjective_response(
        self,
        question=None,
        marks=None,
        evaluated_at=None,
    ):
        return Response.objects.create(
            attempt=self.attempt,
            question=question or self.subjective_question,
            submitted_answer="Normalization reduces redundancy.",
            marks_obtained=marks,
            evaluated_at=evaluated_at,
        )

    def test_pending_subjective_responses_block_finalization(self):
        self.create_subjective_response()

        second_question = Question.objects.create(
            text="Explain indexing.",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="",
            subject="Computer Science",
            topic="DBMS",
            difficulty=Question.Difficulty.EASY,
        )

        ExamQuestion.objects.create(
            exam=self.exam,
            question=second_question,
            position=2,
            marks=5,
        )

        self.create_subjective_response(
            question=second_question,
            marks=None,
            evaluated_at=self.now,
        )

        result = finalize_attempt_score(self.attempt)

        self.assertEqual(
            result,
            {"finalized": False, "pending_count": 2},
        )

        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.is_graded)

    def test_all_graded_subjective_responses_finalize_score(self):
        self.create_subjective_response(
            marks=Decimal("4.00"),
            evaluated_at=self.now,
        )

        result = finalize_attempt_score(self.attempt)

        self.assertTrue(result["finalized"])
        self.assertEqual(self.attempt.subjective_score, Decimal("4.00"))
        self.assertEqual(self.attempt.total_score, Decimal("7.00"))
        self.assertTrue(self.attempt.is_graded)

    def test_negative_objective_score_is_supported(self):
        self.attempt.objective_score = Decimal("-1.00")
        self.attempt.save(update_fields=["objective_score"])

        self.create_subjective_response(
            marks=Decimal("3.00"),
            evaluated_at=self.now,
        )

        finalize_attempt_score(self.attempt)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.total_score, Decimal("2.00"))
        self.assertTrue(self.attempt.is_graded)

    def test_repeated_call_recalculates_after_regrading(self):
        response = self.create_subjective_response(
            marks=Decimal("2.00"),
            evaluated_at=self.now,
        )

        finalize_attempt_score(self.attempt)

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.total_score, Decimal("5.00"))

        response.marks_obtained = Decimal("4.00")
        response.save(update_fields=["marks_obtained"])

        finalize_attempt_score(self.attempt)

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.subjective_score, Decimal("4.00"))
        self.assertEqual(self.attempt.total_score, Decimal("7.00"))

    def test_unsubmitted_attempt_raises_validation_error(self):
        self.attempt.status = Attempt.Status.IN_PROGRESS
        self.attempt.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            finalize_attempt_score(self.attempt)

    def test_decimal_precision_is_preserved(self):
        self.attempt.objective_score = Decimal("0.10")
        self.attempt.save(update_fields=["objective_score"])

        self.create_subjective_response(
            marks=Decimal("0.20"),
            evaluated_at=self.now,
        )

        finalize_attempt_score(self.attempt)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.subjective_score, Decimal("0.20"))
        self.assertEqual(self.attempt.total_score, Decimal("0.30"))

    def test_response_for_question_outside_exam_is_ignored(self):
        self.create_subjective_response(
            marks=Decimal("2.00"),
            evaluated_at=self.now,
        )

        outside_question = Question.objects.create(
            text="Question not belonging to this exam.",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="",
            subject="Computer Science",
            topic="DBMS",
            difficulty=Question.Difficulty.EASY,
        )

        self.create_subjective_response(
            question=outside_question,
        )

        result = finalize_attempt_score(self.attempt)

        self.attempt.refresh_from_db()

        self.assertTrue(result["finalized"])
        self.assertEqual(self.attempt.subjective_score, Decimal("2.00"))
        self.assertEqual(self.attempt.total_score, Decimal("5.00"))

    def test_missing_subjective_response_blocks_finalization(self):
        second_question = Question.objects.create(
            text="Explain indexing.",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="",
            subject="Computer Science",
            topic="DBMS",
            difficulty=Question.Difficulty.EASY,
        )

        ExamQuestion.objects.create(
            exam=self.exam,
            question=second_question,
            position=2,
            marks=5,
        )

        self.create_subjective_response(
            marks=Decimal("4.00"),
            evaluated_at=self.now,
        )

        result = finalize_attempt_score(self.attempt)

        self.assertEqual(
            result,
            {"finalized": False, "pending_count": 1},
        )

        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.is_graded)

    def test_zero_subjective_marks_count_as_graded(self):
        self.create_subjective_response(
            marks=Decimal("0.00"),
            evaluated_at=self.now,
        )

        result = finalize_attempt_score(self.attempt)

        self.assertTrue(result["finalized"])
        self.assertEqual(result["pending_count"], 0)
        self.assertEqual(result["subjective_score"], Decimal("0.00"))

    def test_partially_graded_attempt_reports_pending_count(self):
        second_question = Question.objects.create(
            text="Explain indexing.",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="",
            subject="Computer Science",
            topic="DBMS",
            difficulty=Question.Difficulty.EASY,
        )

        ExamQuestion.objects.create(
            exam=self.exam,
            question=second_question,
            position=2,
            marks=5,
        )

        self.create_subjective_response(
            marks=Decimal("4.00"),
            evaluated_at=self.now,
        )

        result = finalize_attempt_score(self.attempt)

        self.assertEqual(
            result,
            {"finalized": False, "pending_count": 1},
        )

    def test_objective_only_exam_finalizes_with_objective_score(self):
        self.exam.exam_questions.all().delete()

        objective_question = Question.objects.create(
            text="What does SQL stand for?",
            question_type=Question.QuestionType.MCQ,
            options=["Structured Query Language", "Simple Query Language"],
            correct_answer="Structured Query Language",
            subject="Computer Science",
            topic="DBMS",
            difficulty=Question.Difficulty.EASY,
        )

        ExamQuestion.objects.create(
            exam=self.exam,
            question=objective_question,
            position=1,
            marks=5,
        )

        self.attempt.objective_score = Decimal("5.00")
        self.attempt.save(update_fields=["objective_score"])

        result = finalize_attempt_score(self.attempt)

        self.assertTrue(result["finalized"])
        self.assertEqual(result["subjective_score"], Decimal("0.00"))
        self.assertEqual(result["total_score"], Decimal("5.00"))

    def test_expired_attempt_cannot_be_finalized(self):
        self.attempt.status = Attempt.Status.EXPIRED
        self.attempt.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            finalize_attempt_score(self.attempt)