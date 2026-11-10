from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsFaculty, IsFacultyOrAdmin
from exam_management.models import Exam
from reports.exports import EXPORTERS
from reports.services import build_exam_report, build_question_breakdown


class IgnoreAcceptHeader(BaseContentNegotiation):
    """Let file downloads succeed whatever the client's Accept header says."""

    def select_parser(self, request, parsers):
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        return (renderers[0], renderers[0].media_type)


class ExamReportView(APIView):
    """Class performance report for one exam (OEP-F-051)."""

    permission_classes = [IsFacultyOrAdmin]

    def get(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        return Response(build_exam_report(exam), status=status.HTTP_200_OK)


class ExamReportExportView(APIView):
    """Download the exam report as PDF or Excel (OEP-F-052).

    ``?export_format=pdf`` or ``?export_format=xlsx``. (Not ``format``, which
    Django REST framework reserves for choosing a response renderer.)
    """

    permission_classes = [IsFacultyOrAdmin]
    content_negotiation_class = IgnoreAcceptHeader

    def get(self, request, exam_id):
        export_format = request.query_params.get("export_format", "").lower()
        if export_format not in EXPORTERS:
            raise ValidationError({"export_format": "Use pdf or xlsx."})

        exam = get_object_or_404(Exam, pk=exam_id)
        render, content_type = EXPORTERS[export_format]
        response = HttpResponse(render(build_exam_report(exam)), content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="exam-{exam.id}-report.{export_format}"'
        )
        return response


class QuestionBreakdownView(APIView):
    """Question-wise breakdown for one exam, Faculty only (OEP-F-053)."""

    permission_classes = [IsFaculty]

    def get(self, request, exam_id):
        exam = get_object_or_404(Exam, pk=exam_id)
        return Response(build_question_breakdown(exam), status=status.HTTP_200_OK)
