
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
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
        )

        self.assertEqual(question.question_type, "MCQ")
        self.assertEqual(len(question.options), 4)
        self.assertEqual(question.correct_answer, "Python")
        self.assertEqual(question.subject, "Computer Science")
        self.assertEqual(question.topic, "Django")
        self.assertEqual(question.difficulty, "EASY")

    def test_create_true_false_question(self):
        question = Question.objects.create(
            text="Django is a Python web framework.",
            question_type=Question.QuestionType.TRUE_FALSE,
            correct_answer="True",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
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
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.MEDIUM,
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
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.EASY,
        )

        self.assertEqual(
            str(question),
            "Short Answer: What is Python?",
        )


class QuestionAPITests(APITestCase):
    url = "/api/questions/"

    def question_data(self, **overrides):
        data = {
            "text": "Which language is used with Django?",
            "question_type": "MCQ",
            "options": ["Python", "Java", "C++", "Ruby"],
            "correct_answer": "Python",
            "subject": "Computer Science",
            "topic": "Django",
            "difficulty": "EASY",
        }
        data.update(overrides)
        return data

    def test_create_valid_mcq(self):
        response = self.client.post(
            self.url,
            self.question_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(Question.objects.count(), 1)
        self.assertEqual(
            response.data["subject"],
            "Computer Science",
        )
        self.assertEqual(response.data["topic"], "Django")
        self.assertEqual(response.data["difficulty"], "EASY")

    def test_list_questions(self):
        Question.objects.create(
            text="Django uses Python.",
            question_type=Question.QuestionType.TRUE_FALSE,
            correct_answer="True",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
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
            self.question_data(
                text="Choose the language",
                options=["Python"],
                correct_answer="Python",
            ),
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
            self.question_data(
                text="Django is a Python web framework.",
                question_type="TRUE_FALSE",
                options=[],
                correct_answer="True",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_create_short_answer_question(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="What does ORM stand for?",
                question_type="SHORT_ANSWER",
                options=[],
                correct_answer="Object-Relational Mapping",
                difficulty="MEDIUM",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_reject_mcq_answer_not_in_options(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="Choose the language",
                options=["Python", "Java"],
                correct_answer="C++",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_blank_question_text(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="   ",
                question_type="SHORT_ANSWER",
                options=[],
                correct_answer="Object-Relational Mapping",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_invalid_true_false_answer(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="Django is a Python web framework.",
                question_type="TRUE_FALSE",
                options=[],
                correct_answer="Maybe",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_duplicate_mcq_options(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="Choose the language",
                options=["Python", "python", "Java"],
                correct_answer="Python",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_invalid_question_type(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="What is Python?",
                question_type="ESSAY",
                options=[],
                correct_answer="A programming language",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_question_text(self):
        data = self.question_data()
        data.pop("text")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_question_type(self):
        data = self.question_data()
        data.pop("question_type")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_accept_mcq_answer_with_different_case_and_whitespace(self):
        response = self.client.post(
            self.url,
            self.question_data(correct_answer=" python "),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_reject_missing_subject(self):
        data = self.question_data()
        data.pop("subject")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_topic(self):
        data = self.question_data()
        data.pop("topic")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_difficulty(self):
        data = self.question_data()
        data.pop("difficulty")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_invalid_difficulty(self):
        response = self.client.post(
            self.url,
            self.question_data(difficulty="VERY_EASY"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_filter_questions_by_subject(self):
        Question.objects.create(
            text="What is Python?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A programming language",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.EASY,
        )
        Question.objects.create(
            text="What is a derivative?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A rate of change",
            subject="Mathematics",
            topic="Calculus",
            difficulty=Question.Difficulty.MEDIUM,
        )

        response = self.client.get(
            self.url,
            {"subject": "Mathematics"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["subject"],
            "Mathematics",
        )

    def test_filter_questions_by_topic(self):
        Question.objects.create(
            text="What is a variable?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A named storage location",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.EASY,
        )
        Question.objects.create(
            text="What is Django?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A Python web framework",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.MEDIUM,
        )

        response = self.client.get(
            self.url,
            {"topic": "Python"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["topic"], "Python")

    def test_filter_questions_by_difficulty(self):
        Question.objects.create(
            text="Easy question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.EASY,
        )
        Question.objects.create(
            text="Hard question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.HARD,
        )

        response = self.client.get(
            self.url,
            {"difficulty": "HARD"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["difficulty"],
            "HARD",
        )

    def test_filter_questions_by_multiple_tags(self):
        Question.objects.create(
            text="Easy Django question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
        )
        Question.objects.create(
            text="Hard Django question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.HARD,
        )
        Question.objects.create(
            text="Easy maths question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Mathematics",
            topic="Algebra",
            difficulty=Question.Difficulty.EASY,
        )

        response = self.client.get(
            self.url,
            {
                "subject": "Computer Science",
                "topic": "Django",
                "difficulty": "HARD",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["difficulty"],
            "HARD",
        )
