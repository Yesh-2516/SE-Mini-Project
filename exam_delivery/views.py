import os
import platform
import sys
import time
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsFacultyOrAdmin
from exam_delivery.models import Attempt
from exam_delivery.serializers import (
    AutosaveRequestSerializer,
    FlagToggleSerializer,
    SubmitRequestSerializer,
)
from exam_delivery.services import (
    allow_reattempt,
    autosave_responses,
    get_attempt_detail,
    get_attempt_timer,
    get_question_navigator,
    start_exam_attempt,
    submit_attempt,
    toggle_question_flag,
)
from exam_management.models import Exam

User = get_user_model()


class StartExamAttemptView(APIView):
    """Start or resume a timed exam attempt (OEP-F-030, OEP-F-034)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        attempt, is_new = start_exam_attempt(
            exam=exam,
            student=request.user,
        )
        data = get_attempt_detail(
            attempt=attempt,
            student=request.user,
        )
        data["is_new"] = is_new
        http_status = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
        return Response(data, status=http_status)


class AttemptDetailView(APIView):
    """Retrieve attempt paper, timer, and saved responses (OEP-F-030)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        data = get_attempt_detail(
            attempt=attempt,
            student=request.user,
        )
        return Response(data, status=status.HTTP_200_OK)


class AttemptTimerView(APIView):
    """Return server-authoritative timer countdown (OEP-F-030)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        data = get_attempt_timer(
            attempt=attempt,
            student=request.user,
        )
        return Response(data, status=status.HTTP_200_OK)


class AutosaveResponsesView(APIView):
    """Periodically auto-save responses mid-exam (OEP-F-035)."""

    permission_classes = [IsAuthenticated]

    def put(self, request, exam_id, attempt_id):
        return self._handle_autosave(request, exam_id, attempt_id)

    def post(self, request, exam_id, attempt_id):
        return self._handle_autosave(request, exam_id, attempt_id)

    def _handle_autosave(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        serializer = AutosaveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = autosave_responses(
            attempt=attempt,
            student=request.user,
            responses_data=serializer.validated_data["responses"],
        )
        return Response(result, status=status.HTTP_200_OK)


class SubmitExamAttemptView(APIView):
    """Submit exam attempt manually or on timeout (OEP-F-032, OEP-F-033)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        serializer = SubmitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = submit_attempt(
            attempt=attempt,
            student=request.user,
            responses_data=serializer.validated_data.get("responses"),
            reason=serializer.validated_data.get("reason", "manual"),
        )
        return Response(result, status=status.HTTP_200_OK)


class ToggleQuestionFlagView(APIView):
    """Flag or unflag a question for student review (OEP-F-031)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id, attempt_id, question_id):
        return self._handle_flag(request, exam_id, attempt_id, question_id)

    def patch(self, request, exam_id, attempt_id, question_id):
        return self._handle_flag(request, exam_id, attempt_id, question_id)

    def _handle_flag(self, request, exam_id, attempt_id, question_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        serializer = FlagToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = toggle_question_flag(
            attempt=attempt,
            student=request.user,
            question_id=question_id,
            is_flagged=serializer.validated_data.get("is_flagged"),
        )
        return Response(result, status=status.HTTP_200_OK)


class QuestionNavigatorView(APIView):
    """Return overview of all questions with status (OEP-F-031)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        result = get_question_navigator(
            attempt=attempt,
            student=request.user,
        )
        return Response(result, status=status.HTTP_200_OK)


class AllowReattemptView(APIView):
    """Grant re-attempt permission to a student (OEP-F-034)."""

    permission_classes = [IsFacultyOrAdmin]

    def post(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        result = allow_reattempt(
            attempt=attempt,
            user=request.user,
        )
        return Response(result, status=status.HTTP_200_OK)


class AdminDiagnosticsView(APIView):
    """System health and database connectivity diagnostics (OEP-F-063)."""

    permission_classes = [IsAdmin]

    def get(self, request):
        now = timezone.now()

        # Database connectivity check
        db_status = "error"
        db_latency_ms = None
        try:
            start_t = time.perf_counter()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
            latency = (time.perf_counter() - start_t) * 1000
            if row and row[0] == 1:
                db_status = "connected"
                db_latency_ms = round(latency, 2)
        except Exception as e:
            db_status = f"unreachable: {str(e)}"

        active_attempts_count = Attempt.objects.filter(
            status=Attempt.Status.IN_PROGRESS
        ).count()
        total_exams_count = Exam.objects.count()
        total_users_count = User.objects.count()

        return Response(
            {
                "status": "healthy" if db_status == "connected" else "degraded",
                "timestamp": now.isoformat(),
                "server": {
                    "platform": platform.platform(),
                    "python_version": sys.version.split()[0],
                    "django_version": "5.2.18",
                    "status": "operational",
                },
                "database": {
                    "status": db_status,
                    "engine": settings.DATABASES["default"]["ENGINE"],
                    "latency_ms": db_latency_ms,
                },
                "metrics": {
                    "active_attempts": active_attempts_count,
                    "total_exams": total_exams_count,
                    "total_users": total_users_count,
                },
            },
            status=status.HTTP_200_OK,
        )
