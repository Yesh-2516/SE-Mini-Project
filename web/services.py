from django.db.models import Q
from django.utils import timezone

from exam_delivery.models import Attempt
from exam_management.models import Exam
from exam_management.services import (
    get_exams_visible_to_student,
    is_exam_open,
)


def get_latest_attempts(student):
    attempts = Attempt.objects.filter(student=student).order_by("-started_at")
    latest_attempts = {}
    for attempt in attempts:
        latest_attempts.setdefault(attempt.exam_id, attempt)
    return latest_attempts


def get_visible_exams(*, student, now=None, latest_attempts=None):
    """Return the exams a student may see and open.

    Students see only published exams assigned to their own courses.
    An exam they are still sitting stays visible after its window closes.
    """
    now = now or timezone.now()
    if latest_attempts is None:
        latest_attempts = get_latest_attempts(student)

    resumable_exam_ids = [
        attempt.exam_id
        for attempt in latest_attempts.values()
        if attempt.status == Attempt.Status.IN_PROGRESS
        and not attempt.is_expired(now)
    ]

    sittable_ids = get_exams_visible_to_student(student).values("pk")
    return (
        Exam.objects.filter(
            Q(
                pk__in=sittable_ids,
                availability_start__lte=now,
                availability_end__gt=now,
                exam_questions__isnull=False,
            )
            | Q(pk__in=resumable_exam_ids)
        )
        .distinct()
        .order_by("availability_end", "title")
    )


def get_student_exam_rows(*, student, now=None):
    """Return the exams to list on a student's dashboard and their state."""
    now = now or timezone.now()
    latest_attempts = get_latest_attempts(student)
    exams = get_visible_exams(
        student=student,
        now=now,
        latest_attempts=latest_attempts,
    )

    return [
        {"exam": exam, "state": exam_state(exam, latest_attempts.get(exam.id), now)}
        for exam in exams
    ]


def exam_state(exam, attempt, now):
    if attempt is None:
        return "not_started"
    if attempt.status == Attempt.Status.IN_PROGRESS and not attempt.is_expired(now):
        return "in_progress"
    if attempt.allow_reattempt and is_exam_open(exam, now):
        return "reattempt"
    return "finished"
