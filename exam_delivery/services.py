from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from accounts.audit import EVENT_SUBMISSION, record_audit_event, record_integrity_flag
from exam_delivery.models import Attempt, Response
from exam_management.models import Exam
from exam_management.serializers import StudentExamQuestionSerializer
from exam_management.services import (
    ExamNotAvailable,
    ExamNotOpen,
    ensure_student_can_sit,
    is_exam_open,
    shuffle_paper,
)
from question_bank.grading import OBJECTIVE_QUESTION_TYPES, grade_objective_answer
from question_bank.models import Question


class AttemptAlreadyClosed(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "This exam attempt is already submitted or closed."
    default_code = "attempt_already_closed"


class ExamAlreadyAttempted(PermissionDenied):
    default_detail = "A second attempt on the same exam is blocked."
    default_code = "exam_already_attempted"


def _ensure_attempt_owner(attempt, student, message):
    """Allow only the student who owns the attempt.

    A student reaching for someone else's attempt is logged as an integrity
    flag (OEP-NF-004) before the request is refused.
    """
    if getattr(student, "role", None) == "STUDENT" and attempt.student_id != student.id:
        record_integrity_flag(
            student,
            "foreign_attempt_access",
            attempt_id=attempt.id,
            exam_id=attempt.exam_id,
        )
        raise PermissionDenied(message)
    if getattr(student, "role", None) != "STUDENT":
        raise PermissionDenied(message)


def start_exam_attempt(*, exam, student, now=None):
    """Start or resume a student's exam attempt.

    Enforces the availability window (OEP-SR-004), single-attempt rule
    (OEP-F-034), and sets up a server-authoritative timer (OEP-F-030).
    Never exposes correct answers.

    The single-attempt check and the insert run in one transaction under a
    row lock on the student, and the database also carries a partial unique
    constraint (one IN_PROGRESS attempt per exam and student). Two Start
    requests sent at the same moment therefore cannot both create an
    attempt: the second waits and then resumes the first, or, if it lost the
    race at the constraint, resumes the winner.
    """
    now = now or timezone.now()

    if getattr(student, "role", None) != "STUDENT":
        raise PermissionDenied("Only students can start an exam attempt.")

    try:
        attempt, is_new, failure = _start_or_resume_locked(
            exam=exam, student=student, now=now
        )
    except IntegrityError:
        # Lost a race at the unique constraint: another request created the
        # in-progress attempt first. Resume it instead of failing.
        winner = (
            Attempt.objects.filter(
                exam=exam,
                student=student,
                status=Attempt.Status.IN_PROGRESS,
            )
            .order_by("-started_at")
            .first()
        )
        if winner is None:
            raise
        return winner, False

    # Raised only after the transaction has committed, so a timeout
    # auto-submit performed above is kept even when the start is refused.
    if failure == "already_attempted":
        # ``attempt`` is the student's existing attempt in this case.
        record_integrity_flag(
            student,
            "second_attempt_blocked",
            exam_id=exam.id,
            attempt_id=attempt.id,
        )
        raise ExamAlreadyAttempted()
    if failure == "not_open":
        raise ExamNotOpen()
    if failure == "not_available":
        raise ExamNotAvailable()
    return attempt, is_new


def _start_or_resume_locked(*, exam, student, now):
    """Check the attempt rules and create the attempt in one transaction.

    Returns ``(attempt, is_new, failure)``. ``failure`` is None,
    "already_attempted", "not_open", or "not_available".
    When failure is "already_attempted", attempt is the existing attempt.
    """
    with transaction.atomic():
        # Serialise concurrent starts by the same student. SQLite ignores row
        # locks (it serialises writers itself); the unique constraint is the
        # backstop on every database.
        get_user_model()._default_manager.select_for_update().get(pk=student.pk)

        existing_attempt = (
            Attempt.objects.filter(exam=exam, student=student)
            .order_by("-started_at")
            .first()
        )

        if existing_attempt is not None:
            if existing_attempt.status == Attempt.Status.IN_PROGRESS:
                if existing_attempt.is_expired(now):
                    # Auto-submit expired attempt
                    submit_attempt(
                        attempt=existing_attempt,
                        student=student,
                        reason=Attempt.SubmissionReason.TIMEOUT,
                        now=now,
                    )
                    if not existing_attempt.allow_reattempt:
                        return existing_attempt, False, "already_attempted"
                else:
                    # An already-started attempt remains resumable even after
                    # the exam's admission window closes; its own deadline
                    # still applies.
                    return existing_attempt, False, None

            elif not existing_attempt.allow_reattempt:
                return existing_attempt, False, "already_attempted"

        # The availability window governs creation, not resumption.
        if not is_exam_open(exam, now):
            return None, False, "not_open"
        # Only published exams assigned to the student's courses (OEP-F-024).
        try:
            ensure_student_can_sit(exam=exam, student=student)
        except ExamNotAvailable:
            return None, False, "not_available"		

        # Calculate server deadline
        candidate_end = now + timedelta(minutes=exam.duration_minutes)
        ends_at = candidate_end
        if exam.availability_end and exam.availability_end < candidate_end:
            ends_at = exam.availability_end

        attempt = Attempt.objects.create(
            exam=exam,
            student=student,
            status=Attempt.Status.IN_PROGRESS,
            started_at=now,
            ends_at=ends_at,
        )

        if existing_attempt is not None and existing_attempt.allow_reattempt:
            existing_attempt.allow_reattempt = False
            existing_attempt.save(update_fields=["allow_reattempt", "updated_at"])

        exam_questions = exam.exam_questions.select_related("question").order_by("position")
        responses = [
            Response(
                attempt=attempt,
                question=eq.question,
                submitted_answer="",
                is_flagged=False,
            )
            for eq in exam_questions
        ]
        Response.objects.bulk_create(responses)

        return attempt, True, None


def get_attempt_detail(*, attempt, student, now=None):
    """Return attempt details, questions, timer, and saved answers for student."""
    now = now or timezone.now()

    _ensure_attempt_owner(attempt, student, "Only the student who owns this attempt can access it.")

    # Check for timeout auto-submit
    if attempt.status == Attempt.Status.IN_PROGRESS and attempt.is_expired(now):
        submit_attempt(
            attempt=attempt,
            student=attempt.student,
            reason=Attempt.SubmissionReason.TIMEOUT,
            now=now,
        )
        attempt.refresh_from_db()

    exam_questions = (
        attempt.exam.exam_questions.select_related("question")
        .order_by("position")
    )
    responses_by_question_id = {
        resp.question_id: resp
        for resp in attempt.responses.select_related("question")
    }

    questions_data = []
    for eq in exam_questions:
        resp = responses_by_question_id.get(eq.question_id)
        submitted_answer = resp.submitted_answer if resp else ""
        is_flagged = resp.is_flagged if resp else False

        # Options allow-list per OEP-SR-004. True/False always offers the two
        # fixed choices, whatever is stored on the question, so clients render
        # a True/False choice and not a free-text box. Free-text types get none.
        question_type = eq.question.question_type
        if question_type == Question.QuestionType.MCQ:
            options = list(eq.question.options)
        elif question_type == Question.QuestionType.TRUE_FALSE:
            options = ["True", "False"]
        else:
            options = []

        questions_data.append({
            "question_id": eq.question_id,
            "position": eq.position,
            "marks": eq.marks,
            "text": eq.question.text,
            "question_type": eq.question.question_type,
            "options": options,
            "submitted_answer": submitted_answer,
            "is_flagged": is_flagged,
            "is_answered": bool(submitted_answer and submitted_answer.strip()),
        })

    questions_data = shuffle_paper(
        questions_data,
        seed=attempt.id,
    )

    return {
        "attempt_id": attempt.id,
        "exam_id": attempt.exam_id,
        "title": attempt.exam.title,
        "status": attempt.status,
        "started_at": attempt.started_at,
        "ends_at": attempt.ends_at,
        "submitted_at": attempt.submitted_at,
        "submission_reason": attempt.submission_reason,
        "server_time": now,
        "remaining_seconds": attempt.remaining_seconds(now),
        "is_expired": attempt.is_expired(now),
        "questions": questions_data,
    }


def get_attempt_timer(*, attempt, student, now=None):
    """Return server-synchronized countdown timer status."""
    now = now or timezone.now()

    _ensure_attempt_owner(attempt, student, "Only the student who owns this attempt can access its timer.")

    if attempt.status == Attempt.Status.IN_PROGRESS and attempt.is_expired(now):
        submit_attempt(
            attempt=attempt,
            student=attempt.student,
            reason=Attempt.SubmissionReason.TIMEOUT,
            now=now,
        )
        attempt.refresh_from_db()

    return {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "server_time": now,
        "started_at": attempt.started_at,
        "ends_at": attempt.ends_at,
        "remaining_seconds": attempt.remaining_seconds(now),
        "is_expired": attempt.is_expired(now),
    }


def autosave_responses(*, attempt, student, responses_data, now=None):
    """Save responses periodically during the exam (OEP-F-035)."""
    now = now or timezone.now()

    _ensure_attempt_owner(attempt, student, "Only the student who owns this attempt can save responses.")

    if attempt.status != Attempt.Status.IN_PROGRESS:
        raise AttemptAlreadyClosed("Cannot autosave: attempt is already submitted or closed.")

    if attempt.is_expired(now):
        submit_attempt(
            attempt=attempt,
            student=student,
            reason=Attempt.SubmissionReason.TIMEOUT,
            now=now,
        )
        raise AttemptAlreadyClosed("Cannot autosave: exam time has expired.")

    if not isinstance(responses_data, list):
        raise ValidationError({"responses": "Expected a list of response objects."})

    with transaction.atomic():
        responses_by_question_id = {
            resp.question_id: resp
            for resp in attempt.responses.select_for_update()
        }

        updated_count = 0
        for item in responses_data:
            if not isinstance(item, dict):
                continue
            qid = item.get("question_id")
            if qid not in responses_by_question_id:
                raise ValidationError({"question_id": f"Question {qid} is not part of this exam attempt."})

            resp = responses_by_question_id[qid]
            changed = False

            if "submitted_answer" in item and item["submitted_answer"] is not None:
                resp.submitted_answer = str(item["submitted_answer"])
                changed = True
            elif "answer" in item and item["answer"] is not None:
                resp.submitted_answer = str(item["answer"])
                changed = True

            if "is_flagged" in item and item["is_flagged"] is not None:
                resp.is_flagged = bool(item["is_flagged"])
                changed = True

            if changed:
                resp.save(update_fields=["submitted_answer", "is_flagged", "updated_at"])
                updated_count += 1

    return {
        "status": "saved",
        "saved_at": now,
        "updated_count": updated_count,
        "remaining_seconds": attempt.remaining_seconds(now),
    }


def submit_attempt(*, attempt, student, responses_data=None, reason="manual", now=None):
    """Submit an exam attempt manually or on timeout (OEP-F-032, OEP-F-033).

    The owner check runs outside the transaction so that an integrity flag it
    logs is kept even though the request is refused.
    """
    _ensure_attempt_owner(
        attempt,
        student,
        "Only the student who owns this attempt can submit it.",
    )
    return _submit_attempt(
        attempt=attempt,
        student=student,
        responses_data=responses_data,
        reason=reason,
        now=now,
    )


@transaction.atomic
def _submit_attempt(*, attempt, student, responses_data=None, reason="manual", now=None):
    """Body of ``submit_attempt``; runs in one transaction.

    Idempotent: repeating the submission returns the recorded result without error (OEP-NF-002).
    Immediately auto-grades objective questions upon submission (OEP-F-040).
    """
    now = now or timezone.now()

    _ensure_attempt_owner(attempt, student, "Only the student who owns this attempt can submit it.")

    # Idempotent handling (OEP-NF-002)
    if attempt.status == Attempt.Status.SUBMITTED:
        return {
            "status": "submitted",
            "attempt_id": attempt.id,
            "submitted_at": attempt.submitted_at,
            "reason": attempt.submission_reason,
            "already_submitted": True,
            "objective_score": str(attempt.objective_score),
            "is_graded": attempt.is_graded,
        }

    is_expired = attempt.status == Attempt.Status.IN_PROGRESS and attempt.is_expired(now)
    submission_reason = (
        Attempt.SubmissionReason.TIMEOUT
        if is_expired
        else Attempt.SubmissionReason.MANUAL
    )

    # Save final answers only if the attempt has not expired.
    # Late answers sent after ends_at are ignored so only pre-deadline answers are scored.
    if responses_data and not is_expired:
        responses_by_question_id = {
            resp.question_id: resp
            for resp in attempt.responses.select_for_update()
        }
        for item in responses_data:
            if not isinstance(item, dict):
                continue
            qid = item.get("question_id")
            if qid not in responses_by_question_id:
                raise ValidationError({"question_id": f"Question {qid} is not part of this exam attempt."})
            resp = responses_by_question_id[qid]
            ans = item.get("submitted_answer", item.get("answer"))
            if ans is not None:
                resp.submitted_answer = str(ans)
            if "is_flagged" in item and item["is_flagged"] is not None:
                resp.is_flagged = bool(item["is_flagged"])
            resp.save(update_fields=["submitted_answer", "is_flagged", "updated_at"])

    attempt.status = Attempt.Status.SUBMITTED
    attempt.submission_reason = submission_reason
    attempt.submitted_at = now

    # Auto-grade objective questions (OEP-F-040)
    exam_questions = {
        eq.question_id: eq
        for eq in attempt.exam.exam_questions.select_related("question")
    }

    total_objective_score = Decimal("0.00")
    has_subjective = False

    for resp in attempt.responses.select_related("question"):
        eq = exam_questions.get(resp.question_id)
        if not eq:
            continue
        q = resp.question
        if q.question_type in OBJECTIVE_QUESTION_TYPES:
            score = grade_objective_answer(
                question_type=q.question_type,
                correct_answer=q.correct_answer,
                submitted_answer=resp.submitted_answer,
                marks=eq.marks,
                negative_marks=(
                    attempt.exam.negative_marks
                    if attempt.exam.negative_marking_enabled
                    else 0
                ),
            )
            resp.marks_obtained = score
            resp.evaluated_at = now
            resp.save(update_fields=["marks_obtained", "evaluated_at", "updated_at"])
            total_objective_score += score
        else:
            has_subjective = True

    attempt.objective_score = total_objective_score
    if not has_subjective:
        attempt.total_score = total_objective_score
        attempt.is_graded = True
    else:
        attempt.is_graded = False

    attempt.save()

    # OEP-NF-004: only IDs and scores are logged, never answer content.
    record_audit_event(
        EVENT_SUBMISSION,
        actor=student,
        description="Exam attempt submitted",
        metadata={
            "attempt_id": attempt.id,
            "exam_id": attempt.exam_id,
            "reason": str(submission_reason),
            "objective_score": str(attempt.objective_score),
        },
    )

    return {
        "status": "submitted",
        "attempt_id": attempt.id,
        "submitted_at": attempt.submitted_at,
        "reason": attempt.submission_reason,
        "already_submitted": False,
        "objective_score": str(attempt.objective_score),
        "is_graded": attempt.is_graded,
    }


def toggle_question_flag(*, attempt, student, question_id, is_flagged=None):
    """Toggle or set the flag on a question for review (OEP-F-031)."""
    _ensure_attempt_owner(attempt, student, "Only the student who owns this attempt can flag questions.")

    if attempt.status != Attempt.Status.IN_PROGRESS:
        raise AttemptAlreadyClosed("Attempt is already closed.")

    response = attempt.responses.filter(question_id=question_id).first()
    if not response:
        raise ValidationError({"question_id": "Question not part of this exam attempt."})

    if is_flagged is None:
        response.is_flagged = not response.is_flagged
    else:
        response.is_flagged = bool(is_flagged)

    response.save(update_fields=["is_flagged", "updated_at"])
    return {
        "question_id": question_id,
        "is_flagged": response.is_flagged,
    }


def get_question_navigator(*, attempt, student, now=None):
    """Return overview of all questions with answered/flagged status (OEP-F-031)."""
    now = now or timezone.now()

    _ensure_attempt_owner(attempt, student, "Only the student who owns this attempt can access its navigator.")

    exam_questions = (
        attempt.exam.exam_questions.select_related("question")
        .order_by("position")
    )
    responses_by_question_id = {
        resp.question_id: resp
        for resp in attempt.responses.all()
    }

    navigator = []
    for eq in exam_questions:
        resp = responses_by_question_id.get(eq.question_id)
        submitted_answer = resp.submitted_answer if resp else ""
        is_flagged = resp.is_flagged if resp else False
        is_answered = bool(submitted_answer and submitted_answer.strip())

        navigator.append({
            "question_id": eq.question_id,
            "position": eq.position,
            "marks": eq.marks,
            "question_type": eq.question.question_type,
            "is_answered": is_answered,
            "is_flagged": is_flagged,
        })

    navigator = shuffle_paper(
        navigator,
        seed=attempt.id,
    )

    return {
        "attempt_id": attempt.id,
        "status": attempt.status,
        "remaining_seconds": attempt.remaining_seconds(now),
        "total_questions": len(navigator),
        "answered_count": sum(1 for q in navigator if q["is_answered"]),
        "flagged_count": sum(1 for q in navigator if q["is_flagged"]),
        "questions": navigator,
    }


def allow_reattempt(*, attempt, user):
    """Allow an explicit re-attempt by Admin or Faculty (OEP-F-034)."""
    if getattr(user, "role", None) not in ("ADMIN", "FACULTY"):
        raise PermissionDenied("Only Admin or Faculty can allow a re-attempt.")

    attempt.allow_reattempt = True
    attempt.save(update_fields=["allow_reattempt", "updated_at"])
    return {
        "attempt_id": attempt.id,
        "allow_reattempt": attempt.allow_reattempt,
        "message": "Re-attempt permitted for student.",
    }
