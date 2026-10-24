
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from exam_management.models import Exam, ExamQuestion
from exam_management.services import (
    assemble_exam_manually,
    generate_exam_by_rules,
)
from question_bank.models import Question
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.urls import reverse


class ExamAssemblyTests(TestCase):
    def setUp(self):
        self.exam = Exam.objects.create(title="Operating Systems Test")

        self.easy_questions = [
            self.create_question(f"Easy question {i}", "EASY")
            for i in range(1, 4)
        ]
        self.medium_questions = [
            self.create_question(f"Medium question {i}", "MEDIUM")
            for i in range(1, 3)
        ]
        self.hard_questions = [
            self.create_question(f"Hard question {i}", "HARD")
            for i in range(1, 3)
        ]

    def create_question(self, text, difficulty):
        return Question.objects.create(
            text=text,
            question_type=Question.QuestionType.MCQ,
            options=["Option A", "Option B"],
            correct_answer="Option A",
            subject="Computer Science",
            topic="Operating Systems",
            difficulty=difficulty,
        )

    def test_exam_defaults_to_draft(self):
        self.assertEqual(self.exam.status, Exam.Status.DRAFT)

    def test_manual_selection_preserves_requested_order(self):
        selected = [
            self.medium_questions[1],
            self.easy_questions[0],
            self.hard_questions[0],
        ]

        assemble_exam_manually(
            exam=self.exam,
            question_ids=[question.id for question in selected],
        )

        saved = list(
            ExamQuestion.objects.filter(exam=self.exam)
            .select_related("question")
        )

        self.assertEqual(
            [item.question_id for item in saved],
            [question.id for question in selected],
        )
        self.assertEqual(
            [item.position for item in saved],
            [1, 2, 3],
        )
        self.assertEqual(self.exam.status, Exam.Status.DRAFT)

    def test_manual_selection_rejects_empty_list(self):
        with self.assertRaises(ValidationError):
            assemble_exam_manually(exam=self.exam, question_ids=[])

    def test_manual_selection_rejects_duplicate_ids(self):
        question_id = self.easy_questions[0].id

        with self.assertRaises(ValidationError):
            assemble_exam_manually(
                exam=self.exam,
                question_ids=[question_id, question_id],
            )

    def test_manual_selection_rejects_unknown_id(self):
        with self.assertRaises(ValidationError):
            assemble_exam_manually(
                exam=self.exam,
                question_ids=[999999],
            )

    def test_manual_selection_rejects_non_integer_ids(self):
        with self.assertRaises(ValidationError):
            assemble_exam_manually(
                exam=self.exam,
                question_ids=["not-an-id"],
            )

    def test_rule_generation_selects_requested_difficulty_counts(self):
        generate_exam_by_rules(
            exam=self.exam,
            subject="Computer Science",
            topic="Operating Systems",
            difficulty_counts={"EASY": 2, "MEDIUM": 1, "HARD": 1},
        )

        saved = list(
            ExamQuestion.objects.filter(exam=self.exam)
            .select_related("question")
        )

        self.assertEqual(len(saved), 4)
        self.assertEqual(
            sum(item.question.difficulty == "EASY" for item in saved),
            2,
        )
        self.assertEqual(
            sum(item.question.difficulty == "MEDIUM" for item in saved),
            1,
        )
        self.assertEqual(
            sum(item.question.difficulty == "HARD" for item in saved),
            1,
        )
        self.assertEqual(self.exam.status, Exam.Status.DRAFT)

    def test_rule_generation_rejects_insufficient_questions(self):
        with self.assertRaises(ValidationError):
            generate_exam_by_rules(
                exam=self.exam,
                subject="Computer Science",
                topic="Operating Systems",
                difficulty_counts={"EASY": 100},
            )

        self.assertEqual(
            ExamQuestion.objects.filter(exam=self.exam).count(),
            0,
        )

    def test_rule_generation_rejects_zero_total(self):
        with self.assertRaises(ValidationError):
            generate_exam_by_rules(
                exam=self.exam,
                subject="Computer Science",
                topic="Operating Systems",
                difficulty_counts={"EASY": 0, "MEDIUM": 0},
            )

    def test_rule_generation_rejects_invalid_difficulty(self):
        with self.assertRaises(ValidationError):
            generate_exam_by_rules(
                exam=self.exam,
                subject="Computer Science",
                topic="Operating Systems",
                difficulty_counts={"VERY_HARD": 1},
            )

    def test_rule_generation_rejects_negative_count(self):
        with self.assertRaises(ValidationError):
            generate_exam_by_rules(
                exam=self.exam,
                subject="Computer Science",
                topic="Operating Systems",
                difficulty_counts={"EASY": -1},
            )

    def test_manual_selection_replaces_existing_questions(self):
        assemble_exam_manually(
            exam=self.exam,
            question_ids=[self.easy_questions[0].id],
        )
        assemble_exam_manually(
            exam=self.exam,
            question_ids=[self.medium_questions[0].id],
        )

        saved_ids = list(
            ExamQuestion.objects.filter(exam=self.exam)
            .values_list("question_id", flat=True)
        )

        self.assertEqual(saved_ids, [self.medium_questions[0].id])

    def test_failed_generation_preserves_existing_questions(self):
        original_question = self.easy_questions[0]

        assemble_exam_manually(
            exam=self.exam,
            question_ids=[original_question.id],
        )

        with self.assertRaises(ValidationError):
            generate_exam_by_rules(
                exam=self.exam,
                subject="Computer Science",
                topic="Operating Systems",
                difficulty_counts={"EASY": 100},
            )

        saved = list(
            ExamQuestion.objects.filter(exam=self.exam)
            .values_list("question_id", flat=True)
        )

        self.assertEqual(saved, [original_question.id])

    def test_non_draft_exam_cannot_be_assembled(self):
        self.exam.status = "PUBLISHED"
        self.exam.save()

        with self.assertRaises(ValidationError):
            assemble_exam_manually(
                exam=self.exam,
                question_ids=[self.easy_questions[0].id],
            )

        with self.assertRaises(ValidationError):
            generate_exam_by_rules(
                exam=self.exam,
                subject="Computer Science",
                topic="Operating Systems",
                difficulty_counts={"EASY": 1},
            )

        self.assertEqual(
            ExamQuestion.objects.filter(exam=self.exam).count(),
            0,
        )

class ExamAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="exam_admin",
            password="test-password-123",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)

    def test_create_exam_creates_draft(self):
        response = self.client.post(
            reverse("exam-list-create"),
            {"title": "Database Systems Test"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "Database Systems Test")
        self.assertEqual(response.data["status"], Exam.Status.DRAFT)

    def test_list_exams(self):
        Exam.objects.create(title="Operating Systems Test")

        response = self.client.get(reverse("exam-list-create"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_exam_includes_ordered_questions(self):
        exam = Exam.objects.create(title="Computer Networks Test")
        first = Question.objects.create(
            text="First question",
            question_type=Question.QuestionType.MCQ,
            options=["A", "B"],
            correct_answer="A",
            subject="Computer Science",
            topic="Networking",
            difficulty="EASY",
        )
        second = Question.objects.create(
            text="Second question",
            question_type=Question.QuestionType.MCQ,
            options=["A", "B"],
            correct_answer="B",
            subject="Computer Science",
            topic="Networking",
            difficulty="MEDIUM",
        )

        assemble_exam_manually(
            exam=exam,
            question_ids=[second.id, first.id],
        )

        response = self.client.get(
            reverse("exam-detail", kwargs={"pk": exam.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.data["questions"]],
            [second.id, first.id],
        )
        self.assertEqual(
            [item["position"] for item in response.data["questions"]],
            [1, 2],
        )
        self.assertTrue(response.data["questions"])

        for question in response.data["questions"]:
            self.assertNotIn("correct_answer", question)

    def test_manual_assembly_endpoint(self):
        exam = Exam.objects.create(title="Operating Systems Test")
        question = Question.objects.create(
            text="What is a process?",
            question_type=Question.QuestionType.MCQ,
            options=["A", "B"],
            correct_answer="A",
            subject="Computer Science",
            topic="Operating Systems",
            difficulty="EASY",
        )

        response = self.client.post(
            reverse("exam-manual-assembly", kwargs={"pk": exam.id}),
            {"question_ids": [question.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ExamQuestion.objects.filter(exam=exam).count(),
            1,
        )

    def test_generation_endpoint(self):
        exam = Exam.objects.create(title="Operating Systems Test")
        Question.objects.create(
            text="What is a process?",
            question_type=Question.QuestionType.MCQ,
            options=["A", "B"],
            correct_answer="A",
            subject="Computer Science",
            topic="Operating Systems",
            difficulty="EASY",
        )

        response = self.client.post(
            reverse("exam-rule-generation", kwargs={"pk": exam.id}),
            {
                "subject": "Computer Science",
                "topic": "Operating Systems",
                "difficulty_counts": {"EASY": 1},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ExamQuestion.objects.filter(exam=exam).count(),
            1,
        )

    def test_exam_endpoints_require_staff_access(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(reverse("exam-list-create"))

        self.assertEqual(response.status_code, 403)

    def test_non_staff_user_cannot_access_exam_endpoints(self):
        User = get_user_model()
        regular_user = User.objects.create_user(
            username="regular_exam_user",
            password="test-password-123",
            is_staff=False,
        )

        self.client.force_authenticate(user=regular_user)

        response = self.client.get(reverse("exam-list-create"))

        self.assertEqual(response.status_code, 403)


    def test_create_exam_saves_scoring_settings(self):
        response = self.client.post(
            reverse("exam-list-create"),
            {
                "title": "Scoring Settings Test",
                "duration_minutes": 90,
                "negative_marking_enabled": True,
                "negative_marks": "0.50",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["duration_minutes"], 90)
        self.assertTrue(response.data["negative_marking_enabled"])
        self.assertEqual(str(response.data["negative_marks"]), "0.50")

    def test_update_exam_duration_and_negative_marking(self):
        exam = Exam.objects.create(title="Settings Update Test")

        response = self.client.patch(
            reverse("exam-detail", kwargs={"pk": exam.id}),
            {
                "duration_minutes": 45,
                "negative_marking_enabled": True,
                "negative_marks": "0.25",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        exam.refresh_from_db()
        self.assertEqual(exam.duration_minutes, 45)
        self.assertTrue(exam.negative_marking_enabled)
        self.assertEqual(str(exam.negative_marks), "0.25")

    def test_update_exam_rejects_zero_duration(self):
        exam = Exam.objects.create(title="Invalid Duration Test")

        response = self.client.patch(
            reverse("exam-detail", kwargs={"pk": exam.id}),
            {"duration_minutes": 0},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_update_exam_rejects_zero_penalty_when_enabled(self):
        exam = Exam.objects.create(title="Invalid Penalty Test")

        response = self.client.patch(
            reverse("exam-detail", kwargs={"pk": exam.id}),
            {
                "negative_marking_enabled": True,
                "negative_marks": "0.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_update_question_marks_and_calculate_total(self):
        exam = Exam.objects.create(title="Question Marks Test")
        questions = [
            Question.objects.create(
                text=f"Question {i}",
                question_type=Question.QuestionType.MCQ,
                options=["A", "B"],
                correct_answer="A",
                subject="Computer Science",
                topic="Testing",
                difficulty="EASY",
            )
            for i in range(1, 3)
        ]

        assemble_exam_manually(
            exam=exam,
            question_ids=[question.id for question in questions],
        )

        ExamQuestion.objects.filter(
            exam=exam,
            question=questions[0],
        ).update(marks=2)

        response = self.client.patch(
            reverse(
                "exam-question-marks",
                kwargs={
                    "pk": exam.id,
                    "question_id": questions[1].id,
                },
            ),
            {"marks": 5},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["marks"], 5)
        self.assertEqual(response.data["total_marks"], 7)

        exam.refresh_from_db()
        self.assertEqual(exam.total_marks, 7)

    def test_question_marks_endpoint_rejects_zero_marks(self):
        exam = Exam.objects.create(title="Invalid Question Marks Test")
        question = Question.objects.create(
            text="Question for marks validation",
            question_type=Question.QuestionType.MCQ,
            options=["A", "B"],
            correct_answer="A",
            subject="Computer Science",
            topic="Testing",
            difficulty="EASY",
        )

        assemble_exam_manually(
            exam=exam,
            question_ids=[question.id],
        )

        response = self.client.patch(
            reverse(
                "exam-question-marks",
                kwargs={
                    "pk": exam.id,
                    "question_id": question.id,
                },
            ),
            {"marks": 0},
            format="json",
        )

        self.assertEqual(response.status_code, 400)


    def test_published_exam_settings_cannot_be_updated(self):
        exam = Exam.objects.create(
            title="Published Exam",
            status="PUBLISHED",
        )

        response = self.client.patch(
            reverse("exam-detail", kwargs={"pk": exam.id}),
            {"duration_minutes": 30},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        exam.refresh_from_db()
        self.assertEqual(exam.duration_minutes, 60)

    def test_published_exam_question_marks_cannot_be_updated(self):
        exam = Exam.objects.create(
            title="Published Exam Marks",
            status="PUBLISHED",
        )
        question = Question.objects.create(
            text="Published exam question",
            question_type=Question.QuestionType.MCQ,
            options=["A", "B"],
            correct_answer="A",
            subject="Computer Science",
            topic="Testing",
            difficulty="EASY",
        )
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            position=1,
            marks=2,
        )

        response = self.client.patch(
            reverse(
                "exam-question-marks",
                kwargs={
                    "pk": exam.id,
                    "question_id": question.id,
                },
            ),
            {"marks": 5},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        exam_question = ExamQuestion.objects.get(
            exam=exam,
            question=question,
        )
        self.assertEqual(exam_question.marks, 2)
