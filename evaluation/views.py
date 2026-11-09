from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsFacultyOrAdmin, IsStudent
from evaluation.scorecard import get_scorecard, list_scorecards
from evaluation.serializers import EvaluateResponseSerializer
from evaluation.subjective import evaluate_response, get_grading_queue
from exam_delivery.models import Attempt


class GradingQueueView(APIView):
    """Subjective responses waiting for manual grading (OEP-F-041)."""

    permission_classes = [IsFacultyOrAdmin]

    def get(self, request):
        exam_id = request.query_params.get("exam_id")
        if exam_id is not None:
            try:
                exam_id = int(exam_id)
            except ValueError:
                raise ValidationError({"exam_id": "Must be a whole number."})
        return Response(get_grading_queue(exam_id=exam_id), status=status.HTTP_200_OK)


class EvaluateResponseView(APIView):
    """Award marks and feedback on a subjective response (OEP-F-042)."""

    permission_classes = [IsFacultyOrAdmin]

    def patch(self, request, response_id):
        serializer = EvaluateResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = evaluate_response(
            response_id=response_id,
            evaluator=request.user,
            marks=serializer.validated_data["marks"],
            feedback=serializer.validated_data.get("feedback"),
        )
        return Response(result, status=status.HTTP_200_OK)


class ScorecardListView(APIView):
    """The student's own scorecards that are ready to view (OEP-F-050)."""

    permission_classes = [IsStudent]

    def get(self, request):
        return Response(
            {"scorecards": list_scorecards(student=request.user)},
            status=status.HTTP_200_OK,
        )


class ScorecardDetailView(APIView):
    """One scorecard: total score and per-question marks (OEP-F-050)."""

    permission_classes = [IsStudent]

    def get(self, request, attempt_id):
        attempt = get_object_or_404(
            Attempt.objects.select_related("exam"),
            pk=attempt_id,
        )
        return Response(
            get_scorecard(attempt=attempt, student=request.user),
            status=status.HTTP_200_OK,
        )
