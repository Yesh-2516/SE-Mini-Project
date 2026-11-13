"""Web pages for grading, results, class reports and the audit log.

Each page calls the same service function as its API endpoint, so the rules
(who may grade, when a scorecard is ready, which attempts a report counts)
are enforced in one place:

- Grading queue and grading form: ``evaluation.subjective`` (OEP-F-041, F-042)
- Student results and scorecard: ``evaluation.scorecard`` (OEP-F-050)
- Class report and export links: ``reports.services`` (OEP-F-051, F-052)
- Audit log: ``accounts.audit_models.AuditLog`` (OEP-F-062, NF-004)
"""

from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from rest_framework.exceptions import APIException

from accounts.audit_models import AuditLog
from accounts.models import User
from evaluation.scorecard import ScorecardNotReady, get_scorecard, list_scorecards
from evaluation.subjective import evaluate_response, get_grading_queue
from exam_delivery.models import Attempt
from exam_management.models import Exam
from reports.services import build_exam_report

AUDIT_PAGE_SIZE = 100
AUDIT_EVENT_LABELS = {
    "login.success": "Login",
    "exam.submitted": "Exam submitted",
    "evaluation.updated": "Answer graded",
    "integrity.flag": "Integrity flag",
}


def roles_required(*roles):
    """Allow only logged-in users with one of ``roles``; others get 403."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


staff_only = roles_required(User.Role.FACULTY, User.Role.ADMIN)
student_only = roles_required(User.Role.STUDENT)
admin_only = roles_required(User.Role.ADMIN)


def error_text(exc):
    """Flatten a DRF error detail (str, list or dict) into one sentence."""

    detail = getattr(exc, "detail", exc)
    if isinstance(detail, dict):
        return " ".join(error_text(value) for value in detail.values())
    if isinstance(detail, (list, tuple)):
        return " ".join(error_text(value) for value in detail)
    return str(detail)


def _optional_exam_id(request):
    raw = request.GET.get("exam_id") or request.POST.get("exam_id")
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


# --- Faculty and Admin: grading -------------------------------------------


@never_cache
@staff_only
def grading_queue(request):
    exam_id = _optional_exam_id(request)
    queue = get_grading_queue(exam_id=exam_id)
    return render(
        request,
        "web/grading_queue.html",
        {"queue": queue, "exam_id": exam_id},
    )


@require_POST
@staff_only
def grade_response(request, response_id):
    back = reverse("web-grading")
    exam_id = _optional_exam_id(request)
    if exam_id is not None:
        back = f"{back}?exam_id={exam_id}"

    try:
        marks = Decimal(request.POST.get("marks", "").strip())
    except InvalidOperation:
        messages.error(request, "Enter the marks as a number, for example 3 or 2.5.")
        return redirect(back)
    if not marks.is_finite():
        messages.error(request, "Enter the marks as a number, for example 3 or 2.5.")
        return redirect(back)

    try:
        result = evaluate_response(
            response_id=response_id,
            evaluator=request.user,
            marks=marks,
            feedback=request.POST.get("feedback", "").strip(),
        )
    except APIException as exc:
        messages.error(request, f"Not saved: {error_text(exc)}")
        return redirect(back)

    attempt = result["attempt"]
    text = f"Saved {result['marks_obtained']} / {result['max_marks']} marks."
    if attempt["finalized"]:
        text += (
            f" That attempt is fully graded: total score {attempt['total_score']}."
            " The student can now see their scorecard."
        )
    else:
        text += f" {attempt['pending_count']} more answer(s) in that attempt still need grading."
    messages.success(request, text)
    return redirect(back)


# --- Faculty and Admin: class reports -------------------------------------


@never_cache
@staff_only
def report_list(request):
    exams = Exam.objects.annotate(
        submitted=Count(
            "attempts__student",
            filter=Q(attempts__status=Attempt.Status.SUBMITTED),
            distinct=True,
        ),
        graded=Count(
            "attempts__student",
            filter=Q(
                attempts__status=Attempt.Status.SUBMITTED,
                attempts__is_graded=True,
            ),
            distinct=True,
        ),
    ).order_by("-created_at", "-id")
    return render(request, "web/report_list.html", {"exams": exams})


@never_cache
@staff_only
def report_detail(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    report = build_exam_report(exam)
    largest_bucket = max((row["students"] for row in report["distribution"]), default=0)
    for row in report["distribution"]:
        row["bar"] = round(row["students"] * 100 / largest_bucket) if largest_bucket else 0

    export_url = reverse("report-exam-export", args=[exam.id])
    return render(
        request,
        "web/report_detail.html",
        {
            "exam": exam,
            "report": report,
            "xlsx_url": f"{export_url}?export_format=xlsx",
            "pdf_url": f"{export_url}?export_format=pdf",
        },
    )


# --- Student: results ------------------------------------------------------


@never_cache
@student_only
def my_results(request):
    waiting = (
        Attempt.objects.filter(
            student=request.user,
            status=Attempt.Status.SUBMITTED,
            is_graded=False,
        )
        .select_related("exam")
        .order_by("-submitted_at", "-id")
    )
    return render(
        request,
        "web/results.html",
        {
            "scorecards": list_scorecards(student=request.user),
            "waiting": waiting,
        },
    )


@never_cache
@student_only
def scorecard(request, attempt_id):
    # Another student's attempt is a 404, so attempt IDs can't be probed.
    attempt = get_object_or_404(
        Attempt.objects.select_related("exam"),
        pk=attempt_id,
        student=request.user,
    )
    try:
        card = get_scorecard(attempt=attempt, student=request.user)
    except ScorecardNotReady:
        messages.info(
            request,
            f"Your result for “{attempt.exam.title}” isn't ready yet. "
            "It appears here once your teacher has graded every answer.",
        )
        return redirect("web-results")
    return render(request, "web/scorecard.html", {"card": card})


# --- Admin: audit log ------------------------------------------------------


@never_cache
@admin_only
def audit_log(request):
    event_type = request.GET.get("event_type", "")
    if event_type and event_type not in AUDIT_EVENT_LABELS:
        raise Http404

    logs = AuditLog.objects.select_related("actor").order_by("-created_at", "-id")
    if event_type:
        logs = logs.filter(event_type=event_type)

    entries = [
        {"log": log, "label": AUDIT_EVENT_LABELS.get(log.event_type, log.event_type)}
        for log in logs[:AUDIT_PAGE_SIZE]
    ]
    return render(
        request,
        "web/audit_log.html",
        {
            "entries": entries,
            "event_type": event_type,
            "event_choices": AUDIT_EVENT_LABELS.items(),
            "page_size": AUDIT_PAGE_SIZE,
        },
    )
