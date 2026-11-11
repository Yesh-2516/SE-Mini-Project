"""OEP-F-050 / TC-Result-01: individual student scorecard."""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course
from evaluation.testing import EvaluationWorldMixin, make_question
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question


class ScorecardTests(EvaluationWorldMixin, APITestCase):
    def setUp(self):
        self.create_world()
        self.attempt = self.make_attempt(self.student)
        self.url = f"/api/results/{self.attempt.id}/"

    def evaluate_everything(self):
        self.client.force_authenticate(user=self.faculty)
        for question, marks, feedback in (
            (self.short_a, "4.50", "Good, but give an example."),
            (self.short_b, "3", "Complete."),
        ):
            response = self.response_for(self.attempt, question)
            self.client.patch(
                self.grade_url(response),
                {"marks": marks, "feedback": feedback},
                format="json",
            )
        self.client.force_authenticate(user=self.student)

    def test_scorecard_shows_total_score_and_per_question_marks(self):
        self.evaluate_everything()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["exam_title"], "Mixed Exam")
        self.assertEqual(Decimal(str(response.data["total_score"])), Decimal("9.50"))
        self.assertEqual(
            Decimal(str(response.data["objective_score"])), Decimal("2.00")
        )
        self.assertEqual(
            Decimal(str(response.data["subjective_score"])), Decimal("7.50")
        )
        self.assertEqual(response.data["max_score"], 10)

        marks = {
            q["question_id"]: (Decimal(str(q["marks_obtained"])), q["max_marks"])
            for q in response.data["questions"]
        }
        self.assertEqual(marks[self.mcq.id], (Decimal("2.00"), 2))
        self.assertEqual(marks[self.short_a.id], (Decimal("4.50"), 5))
        self.assertEqual(marks[self.short_b.id], (Decimal("3.00"), 3))

    def test_scorecard_includes_faculty_feedback(self):
        self.evaluate_everything()

        response = self.client.get(self.url)

        feedback = {q["question_id"]: q["feedback"] for q in response.data["questions"]}
        self.assertEqual(feedback[self.short_a.id], "Good, but give an example.")

    def test_questions_are_listed_in_exam_order(self):
        self.evaluate_everything()

        response = self.client.get(self.url)

        positions = [q["position"] for q in response.data["questions"]]
        self.assertEqual(positions, [1, 2, 3])

    def test_scorecard_never_exposes_correct_answers(self):
        self.evaluate_everything()

        response = self.client.get(self.url)

        self.assertNotIn("correct_answer", str(response.data))
        self.assertNotIn("model answer A", str(response.data))

    def test_scorecard_is_not_available_before_evaluation_is_complete(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertNotIn("total_score", response.data)

    def test_scorecard_stays_hidden_while_one_answer_is_unevaluated(self):
        self.client.force_authenticate(user=self.faculty)
        one = self.response_for(self.attempt, self.short_a)
        self.client.patch(self.grade_url(one), {"marks": "4"}, format="json")

        self.client.force_authenticate(user=self.student)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_student_cannot_see_another_students_scorecard(self):
        self.evaluate_everything()
        self.client.force_authenticate(user=self.other_student)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("total_score", response.data)

    def test_faculty_and_admin_use_the_staff_endpoints_not_the_scorecard(self):
        self.evaluate_everything()
        for staff in (self.faculty, self.admin):
            with self.subTest(role=staff.role):
                self.client.force_authenticate(user=staff)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_see_a_scorecard(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_attempt_returns_404(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get("/api/results/999999/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_objective_only_exam_has_a_scorecard_straight_after_submission(self):
        exam = Exam.objects.create(title="Objective Only", duration_minutes=30)
        question = make_question(
            "2 + 2 = ?",
            Question.QuestionType.MCQ,
            correct_answer="4",
            options=["3", "4"],
        )
        ExamQuestion.objects.create(exam=exam, question=question, position=1, marks=2)
        attempt = self.make_attempt(self.student, exam=exam)
        attempt.is_graded = True
        attempt.total_score = Decimal("2.00")
        attempt.save()
        self.client.force_authenticate(user=self.student)

        response = self.client.get(f"/api/results/{attempt.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(response.data["total_score"])), Decimal("2.00"))

    def test_list_shows_only_my_graded_scorecards(self):
        # Graded attempt for me, ungraded for me, graded for someone else.
        self.evaluate_everything()
        other_attempt = self.make_attempt(self.other_student)
        other_attempt.is_graded = True
        other_attempt.save()
        second_exam = Exam.objects.create(title="Second", duration_minutes=30)
        ExamQuestion.objects.create(
            exam=second_exam,
            question=make_question("Define a queue.", Question.QuestionType.SHORT_ANSWER),
            position=1,
            marks=4,
        )
        self.make_attempt(self.student, exam=second_exam)

        response = self.client.get("/api/results/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [item["attempt_id"] for item in response.data["scorecards"]]
        self.assertEqual(ids, [self.attempt.id])
        self.assertEqual(response.data["scorecards"][0]["max_score"], 10)

    def test_list_is_empty_when_nothing_is_graded(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get("/api/results/")

        self.assertEqual(response.data["scorecards"], [])


class EndToEndTests(EvaluationWorldMixin, APITestCase):
    """Student sits the exam, faculty grades it, student sees the scorecard."""

    def setUp(self):
        self.create_world()
        now = timezone.now()
        self.exam.availability_start = now - timedelta(minutes=5)
        self.exam.availability_end = now + timedelta(hours=1)
        self.exam.save()

        # OEP-F-024: the student may sit only published exams assigned to their courses.
        course = Course.objects.create(code="E2E101", name="Evaluation End-to-End")
        course.students.add(self.student)
        self.exam.courses.add(course)
        self.exam.status = Exam.Status.PUBLISHED
        self.exam.save(update_fields=["status"])

    def test_full_flow(self):
        # Student sits and submits the exam.
        self.client.force_authenticate(user=self.student)
        started = self.client.post(f"/api/exams/{self.exam.id}/start/")
        self.assertEqual(started.status_code, status.HTTP_201_CREATED)
        attempt_id = started.data["attempt_id"]
        submitted = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/",
            {
                "responses": [
                    {"question_id": self.mcq.id, "submitted_answer": "Central Processing Unit"},
                    {"question_id": self.short_a.id, "submitted_answer": "Many forms."},
                    {"question_id": self.short_b.id, "submitted_answer": "Hiding data."},
                ]
            },
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        self.assertFalse(submitted.data["is_graded"])

        # No scorecard yet.
        scorecard_url = f"/api/results/{attempt_id}/"
        self.assertEqual(
            self.client.get(scorecard_url).status_code, status.HTTP_409_CONFLICT
        )

        # Faculty finds both answers in the queue and grades them.
        self.client.force_authenticate(user=self.faculty)
        queue = self.client.get("/api/evaluation/pending/")
        self.assertEqual(queue.data["total_pending"], 2)
        for item in queue.data["exams"][0]["responses"]:
            graded = self.client.patch(
                f"/api/evaluation/responses/{item['response_id']}/",
                {"marks": "1", "feedback": "ok"},
                format="json",
            )
            self.assertEqual(graded.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/evaluation/pending/").data["total_pending"], 0)

        # Student now sees the scorecard.
        self.client.force_authenticate(user=self.student)
        card = self.client.get(scorecard_url)
        self.assertEqual(card.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(str(card.data["total_score"])), Decimal("4.00"))
