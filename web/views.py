from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from accounts.audit import client_ip, record_audit_event
from accounts.backends import find_account
from accounts.lockout import is_locked
from accounts.models import User
from web.forms import LoginForm
from web.services import get_student_exam_rows, get_visible_exams


def safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse("web-dashboard")


@sensitive_post_parameters("password")
@require_http_methods(["GET", "POST"])
def login_page(request):
    """Log in through the same backend and lockout rules as the API."""

    if request.user.is_authenticated:
        return redirect("web-dashboard")

    form = LoginForm(request.POST or None)
    error = None
    http_status = 200

    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"]
        user = authenticate(
            request,
            username=identifier,
            password=form.cleaned_data["password"],
        )

        if user is not None:
            login(request, user)
            record_audit_event(
                "login.success",
                actor=user,
                description="User logged in successfully",
                ip_address=client_ip(request),
            )
            return redirect(safe_next_url(request))

        account = find_account(identifier)
        if account is not None and is_locked(account):
            error = "This account is temporarily locked. Try again later."
            http_status = 423
        else:
            error = "Those details don't match an account."
            http_status = 401

    return render(
        request,
        "web/login.html",
        {
            "form": form,
            "error": error,
            "next": request.POST.get("next") or request.GET.get("next", ""),
        },
        status=http_status,
    )


@require_POST
def logout_page(request):
    logout(request)
    return redirect("web-login")


@login_required
def dashboard(request):
    context = {}
    if request.user.role == User.Role.STUDENT:
        context["exam_rows"] = get_student_exam_rows(student=request.user)
    return render(request, "web/dashboard.html", context)


@login_required
def take_exam(request, exam_id):
    """Serve the exam page. Questions only load through the delivery API."""

    if request.user.role != User.Role.STUDENT:
        raise PermissionDenied

    exam = get_object_or_404(get_visible_exams(student=request.user), pk=exam_id)
    return render(request, "web/exam.html", {"exam": exam})
