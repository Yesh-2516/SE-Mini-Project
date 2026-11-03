"""Create the students and exams the browser checks use, and print their ids.

Run by run.js with `manage.py shell`, against the throwaway database. The
usability test in docs/usability_test.md uses the same data.
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

User = get_user_model()
PASSWORD = "Str0ng-Passphrase!"
now = timezone.now()

# One student per check, so an attempt in one check can't affect another.
STUDENTS = [
    "axe", "sitting", "keyboard", "resume", "retry", "submit_error",
    "session", "timeout", "xss", "mobile",
    # For the usability test with real people (docs/usability_test.md).
    "participant1", "participant2", "participant3",
]
for name in STUDENTS:
    User.objects.create_user(
        username=f"student_{name}",
        password=PASSWORD,
        role=User.Role.STUDENT,
    )


def question(text, kind, options=(), answer="Paris"):
    return Question.objects.create(
        text=text,
        question_type=kind,
        options=list(options),
        correct_answer=answer,
        subject="General",
        topic="Sample",
        difficulty=Question.Difficulty.EASY,
    )


def exam(title, questions, minutes=30, starts_in=-10, ends_in=120):
    created = Exam.objects.create(
        title=title,
        duration_minutes=minutes,
        availability_start=now + timedelta(minutes=starts_in),
        availability_end=now + timedelta(minutes=ends_in),
    )
    for position, item in enumerate(questions, start=1):
        ExamQuestion.objects.create(
            exam=created, question=item, position=position, marks=position
        )
    return created


Q = Question.QuestionType
sample = exam("Sample exam", [
    question("What is the capital of France?", Q.MCQ, ["Paris", "Rome", "Madrid"]),
    question("The Earth orbits the Sun.", Q.TRUE_FALSE, ["True", "False"], "True"),
    question("Water is made of hydrogen and ____.", Q.FILL_IN_THE_BLANK, answer="oxygen"),
    question("Explain why the sky is blue.", Q.SHORT_ANSWER, answer="Scattering"),
])
timed = exam("One-minute exam", [
    question("Pick the first letter.", Q.MCQ, ["A", "B"], "A"),
], minutes=1)
script = exam("Script exam", [
    question('<img src=x onerror="window.__injected=1">Pick one', Q.MCQ, ["Yes", "No"], "Yes"),
])
future = exam("Future exam", [
    question("Not yet.", Q.MCQ, ["Yes", "No"], "Yes"),
], starts_in=1440, ends_in=1500)

print("SEED " + json.dumps({
    "password": PASSWORD,
    "sample": sample.id,
    "timed": timed.id,
    "script": script.id,
    "future": future.id,
}))
