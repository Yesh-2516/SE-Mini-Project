"""OEP-F-041 / TC-Eval-02: subjective responses are routed to faculty."""

from rest_framework import status
from rest_framework.test import APITestCase

from evaluation.testing import EvaluationWorldMixin, make_question
from exam_delivery.models import Attempt
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

QUEUE_URL = "/api/evaluation/pending/"


class GradingQueueTests(EvaluationWorldMixin, APITestCase):
    def setUp(self):
        self.create_world()
        self.attempt = self.make_attempt(self.student)

    def test_subjective_responses_appear_in_the_queue(self):
        self.client.force_authenticate(user=self.faculty)

        response = self.client.get(QUEUE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_pending"], 2)
        question_ids = {
            item["question_id"]
            for item in response.data["exams"][0]["responses"]
        }
        self.assertEqual(question_ids, {self.short_a.id, self.short_b.id})

    def test_objective_responses_are_not_queued(self):
        self.client.force_authenticate(user=self.faculty)

        response = self.client.get(QUEUE_URL)

        queued_types = {
            item["question_type"]
            for item in response.data["exams"][0]["responses"]
        }
        self.assertEqual(queued_types, {Question.QuestionType.SHORT_ANSWER})

    def test_queue_item_carries_what_the_grader_needs(self):
        self.client.force_authenticate(user=self.faculty)

        item = self.client.get(QUEUE_URL).data["exams"][0]["responses"][0]

        self.assertEqual(item["attempt_id"], self.attempt.id)
        self.assertEqual(item["student"]["id"], self.student.id)
        self.assertEqual(item["submitted_answer"], "The student's written answer.")
        self.assertIn(item["max_marks"], {5, 3})
        self.assertIn("response_id", item)

    def test_admin_can_see_the_queue(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(QUEUE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_pending"], 2)

    def test_queue_is_grouped_per_exam(self):
        second_exam = Exam.objects.create(title="Another Exam", duration_minutes=30)
        question = make_question("Define a stack.", Question.QuestionType.SHORT_ANSWER)
        ExamQuestion.objects.create(
            exam=second_exam, question=question, position=1, marks=4
        )
        self.make_attempt(self.other_student, exam=second_exam)
        self.client.force_authenticate(user=self.faculty)

        response = self.client.get(QUEUE_URL)

        groups = {g["exam_id"]: g for g in response.data["exams"]}
        self.assertEqual(set(groups), {self.exam.id, second_exam.id})
        self.assertEqual(groups[self.exam.id]["pending_count"], 2)
        self.assertEqual(groups[second_exam.id]["pending_count"], 1)
        self.assertEqual(response.data["total_pending"], 3)
        for group in groups.values():
            for item in group["responses"]:
                self.assertTrue(item["attempt_id"])

    def test_queue_can_be_narrowed_to_one_exam(self):
        second_exam = Exam.objects.create(title="Another Exam", duration_minutes=30)
        question = make_question("Define a stack.", Question.QuestionType.SHORT_ANSWER)
        ExamQuestion.objects.create(
            exam=second_exam, question=question, position=1, marks=4
        )
        self.make_attempt(self.other_student, exam=second_exam)
        self.client.force_authenticate(user=self.faculty)

        response = self.client.get(QUEUE_URL, {"exam_id": second_exam.id})

        self.assertEqual(response.data["total_pending"], 1)
        self.assertEqual(len(response.data["exams"]), 1)
        self.assertEqual(response.data["exams"][0]["exam_id"], second_exam.id)

    def test_bad_exam_id_is_rejected(self):
        self.client.force_authenticate(user=self.faculty)

        response = self.client.get(QUEUE_URL, {"exam_id": "abc"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_attempts_still_in_progress_are_not_queued(self):
        self.attempt.delete()
        self.make_attempt(self.student, status=Attempt.Status.IN_PROGRESS)
        self.client.force_authenticate(user=self.faculty)

        response = self.client.get(QUEUE_URL)

        self.assertEqual(response.data["total_pending"], 0)
        self.assertEqual(response.data["exams"], [])

    def test_graded_responses_leave_the_queue(self):
        self.client.force_authenticate(user=self.faculty)
        graded = self.response_for(self.attempt, self.short_a)

        grade = self.client.patch(
            self.grade_url(graded), {"marks": "4.00"}, format="json"
        )
        self.assertEqual(grade.status_code, status.HTTP_200_OK)

        queue = self.client.get(QUEUE_URL)
        self.assertEqual(queue.data["total_pending"], 1)
        remaining = {
            item["response_id"]
            for item in queue.data["exams"][0]["responses"]
        }
        self.assertNotIn(graded.id, remaining)

    def test_queue_is_empty_once_everything_is_graded(self):
        self.client.force_authenticate(user=self.faculty)
        for question in (self.short_a, self.short_b):
            graded = self.response_for(self.attempt, question)
            self.client.patch(self.grade_url(graded), {"marks": "1"}, format="json")

        queue = self.client.get(QUEUE_URL)

        self.assertEqual(queue.data["total_pending"], 0)
        self.assertEqual(queue.data["exams"], [])

    def test_zero_marks_counts_as_graded(self):
        self.client.force_authenticate(user=self.faculty)
        graded = self.response_for(self.attempt, self.short_a)

        self.client.patch(self.grade_url(graded), {"marks": "0"}, format="json")

        queue = self.client.get(QUEUE_URL)
        self.assertEqual(queue.data["total_pending"], 1)

    def test_student_cannot_see_the_queue(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get(QUEUE_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_see_the_queue(self):
        response = self.client.get(QUEUE_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
