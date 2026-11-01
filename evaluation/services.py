from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from exam_delivery.models import Attempt
from question_bank.grading import OBJECTIVE_QUESTION_TYPES


TWO_DECIMAL_PLACES = Decimal("0.01")


def _round_score(value):
    return value.quantize(
        TWO_DECIMAL_PLACES,
        rounding=ROUND_HALF_UP,
    )


@transaction.atomic
def finalize_attempt_score(attempt):
    """
    Calculate and store an attempt's final score once all subjective
    responses belonging to the exam have been evaluated.
    """

    locked_attempt = (
        Attempt.objects
        .select_for_update()
        .get(pk=attempt.pk)
    )

    if locked_attempt.status != Attempt.Status.SUBMITTED:
        raise ValidationError(
            "Only submitted attempts can have their final score calculated."
        )

    exam_questions = list(
        locked_attempt.exam.exam_questions.select_related(
            "question"
        )
    )

    subjective_question_ids = {
        eq.question_id
        for eq in exam_questions
        if eq.question.question_type not in OBJECTIVE_QUESTION_TYPES
    }

    responses = list(
        locked_attempt.responses
        .select_related("question")
        .all()
    )

    subjective_responses = [
        response
        for response in responses
        if (
            response.question_id in subjective_question_ids
        )
    ]

    response_question_ids = {
        response.question_id
        for response in subjective_responses
    }

    missing_count = len(
        subjective_question_ids - response_question_ids
    )

    pending_count = missing_count + sum(
        1
        for response in subjective_responses
        if (
            response.evaluated_at is None
            or response.marks_obtained is None
        )
    )

    if pending_count:
        return {
            "finalized": False,
            "pending_count": pending_count,
        }
    
    subjective_score = sum(
        (
            response.marks_obtained
            for response in subjective_responses
        ),
        Decimal("0.00"),
    )

    objective_score = locked_attempt.objective_score

    subjective_score = _round_score(subjective_score)
    total_score = _round_score(
        objective_score + subjective_score
    )

    locked_attempt.subjective_score = subjective_score
    locked_attempt.total_score = total_score
    locked_attempt.is_graded = True

    locked_attempt.save(
        update_fields=[
            "subjective_score",
            "total_score",
            "is_graded",
            "updated_at",
        ]
    )
    attempt.refresh_from_db()

    return {
        "finalized": True,
        "pending_count": 0,
        "objective_score": objective_score,
        "subjective_score": subjective_score,
        "total_score": total_score,
    }