
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from question_bank.models import Question


class QuestionModelTests(TestCase):
    def test_create_mcq_question(self):
        question = Question.objects.create(
            text="Which language is used with Django?",
            question_type=Question.QuestionType.MCQ,
            options=["Python", "Java", "C++", "Ruby"],
            correct_answer="Python",
        )

        self.assertEqual(question.question_type, "MCQ")
        self.assertEqual(len(question.options), 4)
        self.assertEqual(question.correct_answer, "Python")

    def test_create_true_false_question(self):
        question = Question.objects.create(
            text="Django is a Python web framework.",
            question_type=Question.QuestionType.TRUE_FALSE,
            correct_answer="True",
        )

        self.assertEqual(
            question.question_type,
            Question.QuestionType.TRUE_FALSE,
        )
        self.assertEqual(question.correct_answer, "True")

    def test_create_short_answer_question(self):
        question = Question.objects.create(
            text="What does ORM stand for?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Object-Relational Mapping",
        )

        self.assertEqual(
            question.question_type,
            Question.QuestionType.SHORT_ANSWER,
        )
        self.assertEqual(
            question.correct_answer,
            "Object-Relational Mapping",
        )

    def test_question_string_representation(self):
        question = Question(
            text="What is Python?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A programming language",
        )

        self.assertEqual(
            str(question),
            "Short Answer: What is Python?",
        )


class QuestionAPITests(APITestCase):
    url = "/api/questions/"

    def test_create_valid_mcq(self):
        response = self.client.post(
            self.url,
            {
                "text": "Which language is used with Django?",
                "question_type": "MCQ",
                "options": ["Python", "Java", "C++", "Ruby"],
                "correct_answer": "Python",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(Question.objects.count(), 1)

    def test_list_questions(self):
        Question.objects.create(
            text="Django uses Python.",
            question_type=Question.QuestionType.TRUE_FALSE,
            correct_answer="True",
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)

    def test_reject_mcq_with_too_few_options(self):
        response = self.client.post(
            self.url,
            {
                "text": "Choose the language",
                "question_type": "MCQ",
                "options": ["Python"],
                "correct_answer": "Python",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Question.objects.count(), 0)

    def test_create_true_false_question(self):
        response = self.client.post(
            self.url,
            {
                "text": "Django is a Python web framework.",
                "question_type": "TRUE_FALSE",
                "options": [],
                "correct_answer": "True",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_create_short_answer_question(self):
        response = self.client.post(
            self.url,
            {
                "text": "What does ORM stand for?",
                "question_type": "SHORT_ANSWER",
                "options": [],
                "correct_answer": "Object-Relational Mapping",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_reject_mcq_answer_not_in_options(self):
        response = self.client.post(
            self.url,
            {
                "text": "Choose the language",
                "question_type": "MCQ",
                "options": ["Python", "Java"],
                "correct_answer": "C++",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_blank_question_text(self):
        response = self.client.post(
            self.url,
            {
                "text": "   ",
                "question_type": "SHORT_ANSWER",
                "options": [],
                "correct_answer": "Object-Relational Mapping",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_invalid_true_false_answer(self):
        response = self.client.post(
            self.url,
            {
                "text": "Django is a Python web framework.",
                "question_type": "TRUE_FALSE",
                "options": [],
                "correct_answer": "Maybe",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_duplicate_mcq_options(self):
        response = self.client.post(
            self.url,
            {
                "text": "Choose the language",
                "question_type": "MCQ",
                "options": ["Python", "python", "Java"],
                "correct_answer": "Python",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_invalid_question_type(self):
        response = self.client.post(
            self.url,
            {
                "text": "What is Python?",
                "question_type": "ESSAY",
                "options": [],
                "correct_answer": "A programming language",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_question_text(self):
        response = self.client.post(
            self.url,
            {
                "question_type": "SHORT_ANSWER",
                "options": [],
                "correct_answer": "A programming language",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_question_type(self):
        response = self.client.post(
            self.url,
            {
                "text": "What is Python?",
                "options": [],
                "correct_answer": "A programming language",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_accept_mcq_answer_with_different_case_and_whitespace(self):
        response = self.client.post(
            self.url,
            {
                "text": "Which language is used with Django?",
                "question_type": "MCQ",
                "options": ["Python", "Java"],
                "correct_answer": " python ",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
