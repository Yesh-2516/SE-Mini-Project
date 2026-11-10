"""Manual grading of subjective answers.

OEP-F-041: the queue of subjective responses waiting for a faculty member.
OEP-F-042: awarding marks and feedback on one response. Saving an evaluation
calls ``finalize_attempt_score`` (OEP-F-043) inside the same transaction, as
the F-042 integration contract in ``deviations.md`` requires.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError

from accounts.audit import EVENT_EVALUATION, record_audit_event
from evaluation.services import finalize_attempt_score
from exam_delivery.models import Attempt, Response
from exam_management.models import ExamQuestion
from question_bank.grading import OBJECTIVE_QUESTION_TYPES

TWO_DECIMAL_PLACES = Decimal("0.01")


class AttemptNotSubmitted(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Only responses from submitted attempts can be evaluated."
    default_code = "attempt_not_submitted"


def _student_summary(student):
    return {
        "id": student.id,
        "name": student.get_full_name() or student.username,
        "roll_number": student.roll_number,
    }


def get_grading_queue(*, exam_id=None):
    """Return pending subjective responses grouped per exam (OEP-F-041).

    A response is pending while it belongs to a submitted attempt, is not an
    objective question type, and has no recorded evaluation. This is the same
    definition ``finalize_attempt_score`` uses, so a graded response leaves the
    queue and the attempt is finalized once the queue holds none of its
    responses.
    """

    pending = (
        Response.objects
        .filter(attempt__status=Attempt.Status.SUBMITTED)
        .filter(Q(evaluated_at__isnull=True) | Q(marks_obtained__isnull=True))
        .exclude(question__question_type__in=OBJECTIVE_QUESTION_TYPES)
        .select_related("attempt__exam", "attempt__student", "question")
        .order_by(
            "attempt__exam__title",
            "attempt__exam_id",
            "attempt__submitted_at",
            "attempt_id",
            "question_id",
        )
    )
    if exam_id is not None:
        pending = pending.filter(attempt__exam_id=exam_id)

    pending = list(pending)

    max_marks = {
        (eq.exam_id, eq.question_id): eq.marks
        for eq in ExamQuestion.objects.filter(
            exam_id__in={resp.attempt.exam_id for resp in pending}
        )
    }

    groups = {}
    total_pending = 0
    for resp in pending:
        attempt = resp.attempt
        marks = max_marks.get((attempt.exam_id, resp.question_id))
        if marks is None:
            # The question was removed from the exam; it is not graded.
            continue

        group = groups.setdefault(
            attempt.exam_id,
            {
                "exam_id": attempt.exam_id,
                "title": attempt.exam.title,
                "pending_count": 0,
                "responses": [],
            },
        )
        group["responses"].append({
            "response_id": resp.id,
            "attempt_id": attempt.id,
            "student": _student_summary(attempt.student),
            "question_id": resp.question_id,
            "question_text": resp.question.text,
            "question_type": resp.question.question_type,
            "max_marks": marks,
            "submitted_answer": resp.submitted_answer,
            "submitted_at": attempt.submitted_at,
        })
        group["pending_count"] += 1
        total_pending += 1

    return {
        "total_pending": total_pending,
        "exams": list(groups.values()),
    }


@transaction.atomic
def evaluate_response(*, response_id, evaluator, marks, feedback=None, now=None):
    """Award marks and feedback on one subjective response (OEP-F-042).

    Marks must be between 0 and the question's marks in this exam. Evaluating
    an already evaluated response is allowed (regrading). The attempt's final
    score is recalculated in the same transaction.
    """

    now = now or timezone.now()

    try:
        response = Response.objects.select_for_update().get(pk=response_id)
    except Response.DoesNotExist:
        raise NotFound("Response not found.")

    attempt = Attempt.objects.select_related("exam").get(pk=response.attempt_id)

    if attempt.status != Attempt.Status.SUBMITTED:
        raise AttemptNotSubmitted()

    if response.question.question_type in OBJECTIVE_QUESTION_TYPES:
        raise ValidationError(
            {"response": "Objective answers are graded automatically."}
        )

    try:
        exam_question = ExamQuestion.objects.get(
            exam_id=attempt.exam_id,
            question_id=response.question_id,
        )
    except ExamQuestion.DoesNotExist:
        raise ValidationError(
            {"response": "This question is no longer part of the exam."}
        )

    marks = Decimal(str(marks)).quantize(TWO_DECIMAL_PLACES)
    max_marks = Decimal(exam_question.marks)
    if marks < 0:
        raise ValidationError({"marks": "Marks cannot be negative."})
    if marks > max_marks:
        raise ValidationError(
            {"marks": f"Marks cannot exceed the question's maximum of {max_marks}."}
        )

    regraded = response.evaluated_at is not None
    previous_marks = response.marks_obtained

    response.marks_obtained = marks
    if feedback is not None:
        response.feedback = feedback
    response.evaluated_by = evaluator
    response.evaluated_at = now
    response.save(
        update_fields=[
            "marks_obtained",
            "feedback",
            "evaluated_by",
            "evaluated_at",
            "updated_at",
        ]
    )

    # OEP-NF-004: log the change (IDs and marks only, no answer content).
    record_audit_event(
        EVENT_EVALUATION,
        actor=evaluator,
        description="Subjective response evaluated" if not regraded else "Subjective response re-evaluated",
        metadata={
            "response_id": response.id,
            "attempt_id": attempt.id,
            "exam_id": attempt.exam_id,
            "question_id": response.question_id,
            "previous_marks": None if previous_marks is None else str(previous_marks),
            "marks": str(marks),
            "regraded": regraded,
        },
    )

    outcome = finalize_attempt_score(attempt)

    attempt_result = {
        "finalized": outcome["finalized"],
        "pending_count": outcome["pending_count"],
    }
    if outcome["finalized"]:
        attempt_result["objective_score"] = outcome["objective_score"]
        attempt_result["subjective_score"] = outcome["subjective_score"]
        attempt_result["total_score"] = outcome["total_score"]

    return {
        "response_id": response.id,
        "attempt_id": attempt.id,
        "question_id": response.question_id,
        "marks_obtained": response.marks_obtained,
        "max_marks": exam_question.marks,
        "feedback": response.feedback,
        "evaluated_by": evaluator.id,
        "evaluated_at": response.evaluated_at,
        "regraded": regraded,
        "attempt": attempt_result,
    }
