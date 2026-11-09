"""Shared fixtures for the evaluation tests (not a test module itself)."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from exam_delivery.models import Attempt, Response
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

User = get_user_model()


def make_question(text, question_type, *, correct_answer="x", options=None):
    return Question.objects.create(
        text=text,
        question_type=question_type,
        options=options or [],
        correct_answer=correct_answer,
        subject="Computer Science",
        topic="Evaluation",
        difficulty=Question.Difficulty.EASY,
    )


class EvaluationWorldMixin:
    """One exam with an MCQ (2 marks) and two short answers (5 and 3 marks)."""

    def create_world(self):
        self.faculty = User.objects.create_user(
            username="eval_faculty",
            email="eval_faculty@example.com",
            password="StrongPassword123!",
            role=User.Role.FACULTY,
        )
        self.admin = User.objects.create_user(
            username="eval_admin",
            email="eval_admin@example.com",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
        )
        self.student = User.objects.create_user(
            username="eval_student",
            email="eval_student@example.com",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
        )
        self.other_student = User.objects.create_user(
            username="eval_other_student",
            email="eval_other_student@example.com",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
        )

        self.exam = Exam.objects.create(title="Mixed Exam", duration_minutes=30)
        self.mcq = make_question(
            "What does CPU stand for?",
            Question.QuestionType.MCQ,
            correct_answer="Central Processing Unit",
            options=["Central Processing Unit", "Computer Personal Unit"],
        )
        self.short_a = make_question(
            "Explain polymorphism.",
            Question.QuestionType.SHORT_ANSWER,
            correct_answer="model answer A",
        )
        self.short_b = make_question(
            "Explain encapsulation.",
            Question.QuestionType.SHORT_ANSWER,
            correct_answer="model answer B",
        )
        for position, (question, marks) in enumerate(
            [(self.mcq, 2), (self.short_a, 5), (self.short_b, 3)],
            start=1,
        ):
            ExamQuestion.objects.create(
                exam=self.exam,
                question=question,
                position=position,
                marks=marks,
            )

    def make_attempt(self, student, exam=None, *, status=Attempt.Status.SUBMITTED):
        """A submitted attempt whose MCQ was auto-graded to 2 marks."""

        exam = exam or self.exam
        now = timezone.now()
        attempt = Attempt.objects.create(
            exam=exam,
            student=student,
            status=status,
            started_at=now - timedelta(minutes=20),
            ends_at=now - timedelta(minutes=5),
            submitted_at=(
                now - timedelta(minutes=10)
                if status == Attempt.Status.SUBMITTED
                else None
            ),
            objective_score=Decimal("2.00"),
        )
        for eq in exam.exam_questions.select_related("question"):
            if eq.question.question_type == Question.QuestionType.MCQ:
                Response.objects.create(
                    attempt=attempt,
                    question=eq.question,
                    submitted_answer=eq.question.correct_answer,
                    marks_obtained=Decimal("2.00"),
                    evaluated_at=now,
                )
            else:
                Response.objects.create(
                    attempt=attempt,
                    question=eq.question,
                    submitted_answer="The student's written answer.",
                )
        return attempt

    def response_for(self, attempt, question):
        return Response.objects.get(attempt=attempt, question=question)

    def grade_url(self, response):
        return f"/api/evaluation/responses/{response.id}/"
