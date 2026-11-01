from django.db.models import Q
from django.utils import timezone

from exam_delivery.models import Attempt
from exam_management.models import Exam
from exam_management.services import is_exam_open


def get_student_exam_rows(*, student, now=None):
    """Return the exams to list on a student's dashboard and their state.

    Publishing and course assignment (OEP-F-024) don't exist yet, so every
    open exam with questions is listed for every student.
    """
    now = now or timezone.now()

    attempts = Attempt.objects.filter(student=student).order_by("-started_at")
    latest_attempts = {}
    for attempt in attempts:
        latest_attempts.setdefault(attempt.exam_id, attempt)

    resumable_exam_ids = [
        attempt.exam_id
        for attempt in latest_attempts.values()
        if attempt.status == Attempt.Status.IN_PROGRESS
        and not attempt.is_expired(now)
    ]

    exams = (
        Exam.objects.filter(
            Q(
                availability_start__lte=now,
                availability_end__gt=now,
                exam_questions__isnull=False,
            )
            | Q(pk__in=resumable_exam_ids)
        )
        .distinct()
        .order_by("availability_end", "title")
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
