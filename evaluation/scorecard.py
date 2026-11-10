"""Student scorecards (OEP-F-050).

A scorecard is only available once evaluation is complete (``is_graded``) and
only to the student who sat the attempt. Answer keys are never included
(OEP-SR-004).
"""

from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied

from exam_delivery.models import Attempt


class ScorecardNotReady(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "Your scorecard is not available yet because evaluation is not complete."
    )
    default_code = "scorecard_not_ready"


def get_scorecard(*, attempt, student):
    """Return the scorecard for one of the student's own graded attempts."""

    if getattr(student, "role", None) != "STUDENT" or attempt.student_id != student.id:
        raise PermissionDenied("You can only view your own scorecard.")

    if attempt.status != Attempt.Status.SUBMITTED or not attempt.is_graded:
        raise ScorecardNotReady()

    exam = attempt.exam
    exam_questions = list(
        exam.exam_questions.select_related("question").order_by("position")
    )
    responses = {resp.question_id: resp for resp in attempt.responses.all()}

    questions = []
    for eq in exam_questions:
        resp = responses.get(eq.question_id)
        questions.append({
            "position": eq.position,
            "question_id": eq.question_id,
            "text": eq.question.text,
            "question_type": eq.question.question_type,
            "max_marks": eq.marks,
            "marks_obtained": resp.marks_obtained if resp else None,
            "submitted_answer": resp.submitted_answer if resp else "",
            "feedback": resp.feedback if resp else "",
        })

    return {
        "attempt_id": attempt.id,
        "exam_id": exam.id,
        "exam_title": exam.title,
        "submitted_at": attempt.submitted_at,
        "objective_score": attempt.objective_score,
        "subjective_score": attempt.subjective_score,
        "total_score": attempt.total_score,
        "max_score": sum(eq.marks for eq in exam_questions),
        "questions": questions,
    }


def list_scorecards(*, student):
    """Summaries of the student's own attempts whose evaluation is complete."""

    attempts = (
        Attempt.objects
        .filter(
            student=student,
            status=Attempt.Status.SUBMITTED,
            is_graded=True,
        )
        .select_related("exam")
        .prefetch_related("exam__exam_questions")
        .order_by("-submitted_at", "-id")
    )
    return [
        {
            "attempt_id": attempt.id,
            "exam_id": attempt.exam_id,
            "exam_title": attempt.exam.title,
            "submitted_at": attempt.submitted_at,
            "total_score": attempt.total_score,
            "max_score": attempt.exam.total_marks,
        }
        for attempt in attempts
    ]
