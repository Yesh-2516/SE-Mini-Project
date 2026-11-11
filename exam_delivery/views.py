from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsFacultyOrAdmin, IsStudent
from exam_delivery.diagnostics import collect_diagnostics
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


class StartExamAttemptView(APIView):
    """Start or resume a timed exam attempt (OEP-F-030, OEP-F-034)."""

    permission_classes = [IsStudent]

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

    permission_classes = [IsStudent]

    def get(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        data = get_attempt_detail(
            attempt=attempt,
            student=request.user,
        )
        return Response(data, status=status.HTTP_200_OK)


class AttemptTimerView(APIView):
    """Return server-authoritative timer countdown (OEP-F-030)."""

    permission_classes = [IsStudent]

    def get(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        data = get_attempt_timer(
            attempt=attempt,
            student=request.user,
        )
        return Response(data, status=status.HTTP_200_OK)


class AutosaveResponsesView(APIView):
    """Periodically auto-save responses mid-exam (OEP-F-035)."""

    permission_classes = [IsStudent]

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

    permission_classes = [IsStudent]

    def post(self, request, exam_id, attempt_id):
        attempt = get_object_or_404(Attempt, pk=attempt_id, exam_id=exam_id)
        serializer = SubmitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = submit_attempt(
            attempt=attempt,
            student=request.user,
            responses_data=serializer.validated_data.get("responses"),
        )
        return Response(result, status=status.HTTP_200_OK)


class ToggleQuestionFlagView(APIView):
    """Flag or unflag a question for student review (OEP-F-031)."""

    permission_classes = [IsStudent]

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

    permission_classes = [IsStudent]

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
        return Response(collect_diagnostics(), status=status.HTTP_200_OK)
