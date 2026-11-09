"""Shared fixtures for the reports tests (not a test module itself)."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from exam_delivery.models import Attempt, Response
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

User = get_user_model()


def make_question(text, question_type, correct_answer="x"):
    return Question.objects.create(
        text=text,
        question_type=question_type,
        options=["A", "B"] if question_type == Question.QuestionType.MCQ else [],
        correct_answer=correct_answer,
        subject="Computer Science",
        topic="Reports",
        difficulty=Question.Difficulty.EASY,
    )


def make_user(username, role, **extra):
    # No password: hashing is slow and these users never log in.
    return User.objects.create(username=username, role=role, **extra)


class ReportsWorldMixin:
    """An exam out of 10 (MCQ 2, short answers 5 and 3) and four graded students.

    Marks (MCQ, short A, short B): s1 = 2/5/3 -> 10, s2 = 2/4.5/1 -> 7.5,
    s3 = 0/2/2 -> 4, s4 = 0/0/0 -> 0 (s4 left every answer blank).
    """

    def create_world(self):
        self.faculty = make_user("rep_faculty", User.Role.FACULTY)
        self.admin = make_user("rep_admin", User.Role.ADMIN)
        self.student = make_user("rep_student", User.Role.STUDENT)
        self.exam = Exam.objects.create(title="Mixed Exam", duration_minutes=30)
        self.mcq = make_question("What does CPU stand for?", Question.QuestionType.MCQ)
        self.short_a = make_question("Explain polymorphism.", Question.QuestionType.SHORT_ANSWER)
        self.short_b = make_question("Explain encapsulation.", Question.QuestionType.SHORT_ANSWER)
        for position, (question, marks) in enumerate(
            [(self.mcq, 2), (self.short_a, 5), (self.short_b, 3)], start=1
        ):
            ExamQuestion.objects.create(
                exam=self.exam, question=question, position=position, marks=marks
            )

        self.s1 = self.add_student("s1", "S001", "Asha", "Rao")
        self.s2 = self.add_student("s2", "S002", "Bala", "Iyer")
        self.s3 = self.add_student("s3", "S003", "Chitra", "Nair")
        self.s4 = self.add_student("s4", "S004", "Dev", "Shah")
        self.grade(self.s1, "2", "5", "3")
        self.grade(self.s2, "2", "4.5", "1")
        self.grade(self.s3, "0", "2", "2")
        self.grade(self.s4, "0", "0", "0", answered=False)

    def add_student(self, username, roll_number, first_name, last_name):
        return make_user(
            username,
            User.Role.STUDENT,
            roll_number=roll_number,
            first_name=first_name,
            last_name=last_name,
        )

    def grade(self, student, mcq, short_a, short_b, *, exam=None, graded=True,
              answered=True, started_minutes_ago=30):
        """A submitted attempt with the given marks per question."""

        exam = exam or self.exam
        marks = [Decimal(mcq), Decimal(short_a), Decimal(short_b)]
        now = timezone.now()
        started = now - timedelta(minutes=started_minutes_ago)
        attempt = Attempt.objects.create(
            exam=exam,
            student=student,
            status=Attempt.Status.SUBMITTED,
            started_at=started,
            ends_at=started + timedelta(minutes=30),
            submitted_at=started + timedelta(minutes=20),
            objective_score=marks[0],
            subjective_score=marks[1] + marks[2] if graded else Decimal("0"),
            total_score=sum(marks) if graded else Decimal("0"),
            is_graded=graded,
        )
        for eq, value in zip(exam.exam_questions.order_by("position"), marks):
            Response.objects.create(
                attempt=attempt,
                question=eq.question,
                submitted_answer="An answer." if answered else "",
                marks_obtained=value if graded else None,
                evaluated_at=now if graded else None,
            )
        return attempt
