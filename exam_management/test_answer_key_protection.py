import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from exam_management.models import Exam, ExamQuestion
from exam_management.services import (
    ExamNotOpen,
    get_student_exam_paper,
    is_exam_open,
)
from question_bank.models import Question

User = get_user_model()

# Answers chosen so they appear nowhere else in the question data.
FILL_IN_ANSWER = "mitochondria-7f3a"
SHORT_ANSWER = "photosynthesis-c91e"


def make_exam_with_all_question_types(start, end):
    exam = Exam.objects.create(
        title="Biology Midterm",
        availability_start=start,
        availability_end=end,
    )
    questions = [
        Question.objects.create(
            text="Which organ pumps blood?",
            question_type=Question.QuestionType.MCQ,
            options=["Heart", "Lung", "Liver"],
            correct_answer="Heart",
            subject="Biology",
            topic="Anatomy",
            difficulty=Question.Difficulty.EASY,
        ),
        Question.objects.create(
            text="Cells contain DNA.",
            question_type=Question.QuestionType.TRUE_FALSE,
            options=[],
            correct_answer="True",
            subject="Biology",
            topic="Cells",
            difficulty=Question.Difficulty.EASY,
        ),
        Question.objects.create(
            text="The powerhouse of the cell is the ____.",
            question_type=Question.QuestionType.FILL_IN_THE_BLANK,
            # A careless option entry must not leak the answer either.
            options=[FILL_IN_ANSWER],
            correct_answer=FILL_IN_ANSWER,
            subject="Biology",
            topic="Cells",
            difficulty=Question.Difficulty.MEDIUM,
        ),
        Question.objects.create(
            text="How do plants make food?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            options=[],
            correct_answer=SHORT_ANSWER,
            subject="Biology",
            topic="Plants",
            difficulty=Question.Difficulty.HARD,
        ),
    ]
    for position, question in enumerate(questions, start=1):
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            position=position,
            marks=2,
        )
    return exam


def all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_keys(item)


class ExamWindowTests(TestCase):
    """TC-Sec-04: exam questions are not served outside the window."""

    def setUp(self):
        self.now = timezone.now()
        self.exam = make_exam_with_all_question_types(
            self.now + timedelta(hours=1),
            self.now + timedelta(hours=2),
        )

    def test_paper_is_not_served_before_window_opens(self):
        with self.assertRaises(ExamNotOpen):
            get_student_exam_paper(exam=self.exam, now=self.now)

    def test_paper_is_served_from_the_moment_window_opens(self):
        paper = get_student_exam_paper(
            exam=self.exam,
            now=self.exam.availability_start,
        )

        self.assertEqual(len(paper["questions"]), 4)

    def test_paper_is_not_served_once_window_closes(self):
        with self.assertRaises(ExamNotOpen):
            get_student_exam_paper(
                exam=self.exam,
                now=self.exam.availability_end,
            )

    def test_exam_without_window_is_never_open(self):
        self.exam.availability_start = None
        self.exam.availability_end = None

        self.assertFalse(is_exam_open(self.exam, self.now))
        with self.assertRaises(ExamNotOpen):
            get_student_exam_paper(exam=self.exam, now=self.now)

    def test_not_open_maps_to_403(self):
        self.assertEqual(ExamNotOpen.status_code, status.HTTP_403_FORBIDDEN)


class StudentPaperContentTests(TestCase):
    """TC-Sec-04: responses during the exam contain no correct answers."""

    def setUp(self):
        now = timezone.now()
        self.exam = make_exam_with_all_question_types(
            now - timedelta(minutes=5),
            now + timedelta(hours=1),
        )
        self.paper = get_student_exam_paper(exam=self.exam)

    def test_questions_expose_only_allow_listed_fields(self):
        for question in self.paper["questions"]:
            self.assertEqual(
                set(question),
                {"question_id", "position", "marks", "text", "question_type", "options"},
            )

    def test_no_answer_field_anywhere_in_paper(self):
        keys = set(all_keys(json.loads(json.dumps(self.paper, default=str))))

        self.assertNotIn("correct_answer", keys)
        self.assertFalse({key for key in keys if "answer" in key.lower()})

    def test_free_text_answers_never_appear_in_paper(self):
        rendered = json.dumps(self.paper, default=str)

        self.assertNotIn(FILL_IN_ANSWER, rendered)
        self.assertNotIn(SHORT_ANSWER, rendered)

    def test_options_by_question_type(self):
        options = {
            question["question_type"]: question["options"]
            for question in self.paper["questions"]
        }

        self.assertEqual(options["MCQ"], ["Heart", "Lung", "Liver"])
        self.assertEqual(options["TRUE_FALSE"], ["True", "False"])
        self.assertEqual(options["FILL_IN_THE_BLANK"], [])
        self.assertEqual(options["SHORT_ANSWER"], [])

    def test_questions_keep_exam_order(self):
        self.assertEqual(
            [question["position"] for question in self.paper["questions"]],
            [1, 2, 3, 4],
        )


class StudentApiExposureTests(APITestCase):
    """TC-Sec-04: students cannot reach any endpoint that carries answers."""

    def setUp(self):
        now = timezone.now()
        self.exam = make_exam_with_all_question_types(
            now - timedelta(minutes=5),
            now + timedelta(hours=1),
        )
        self.student = User.objects.create_user(
            username="exam_student",
            password="unused-Passw0rd!",
            role=User.Role.STUDENT,
        )
        self.faculty = User.objects.create_user(
            username="exam_faculty",
            password="unused-Passw0rd!",
            role=User.Role.FACULTY,
        )

    def test_student_gets_no_answers_from_question_or_exam_endpoints(self):
        self.client.force_authenticate(user=self.student)
        question = Question.objects.first()

        for path in (
            "/api/questions/",
            f"/api/questions/{question.id}/",
            "/api/exams/",
            f"/api/exams/{self.exam.id}/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                body = response.content.decode()

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertNotIn("correct_answer", body)
                self.assertNotIn(SHORT_ANSWER, body)

    def test_exam_detail_omits_correct_answers_even_for_faculty(self):
        self.client.force_authenticate(user=self.faculty)

        response = self.client.get(f"/api/exams/{self.exam.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.content.decode()
        self.assertNotIn("correct_answer", body)
        self.assertNotIn(FILL_IN_ANSWER, body)
        self.assertNotIn(SHORT_ANSWER, body)
