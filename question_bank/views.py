
import csv

from django.db import transaction
from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.permissions import IsFacultyOrAdmin
from question_bank.import_utils import parse_question_file
from question_bank.models import Question
from question_bank.serializers import QuestionSerializer

MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


class QuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = QuestionSerializer
    permission_classes = [IsFacultyOrAdmin]

    def get_queryset(self):
        queryset = Question.objects.all().order_by("-created_at")

        subject = self.request.query_params.get("subject")
        topic = self.request.query_params.get("topic")
        difficulty = self.request.query_params.get("difficulty")

        if subject:
            queryset = queryset.filter(subject__iexact=subject.strip())

        if topic:
            queryset = queryset.filter(topic__iexact=topic.strip())

        if difficulty:
            queryset = queryset.filter(difficulty__iexact=difficulty.strip())

        return queryset


@api_view(["GET"])
@permission_classes([IsFacultyOrAdmin])
def download_question_template(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        'attachment; filename="question_import_template.csv"'
    )

    writer = csv.writer(response)
    writer.writerow([
        "text",
        "question_type",
        "options",
        "correct_answer",
        "subject",
        "topic",
        "difficulty",
    ])
    writer.writerow([
        "Which language is used with Django?",
        "MCQ",
        '["Python","Java","C++","Ruby"]',
        "Python",
        "Computer Science",
        "Django",
        "EASY",
    ])

    return response


@api_view(["POST"])
@permission_classes([IsFacultyOrAdmin])
def import_questions(request):
    uploaded_file = request.FILES.get("file")

    if uploaded_file is None:
        return Response(
            {"error": "Upload a file using the 'file' field."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if uploaded_file.size > MAX_IMPORT_FILE_SIZE:
        return Response(
            {"error": "File size exceeds the 5 MB import limit."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validated_questions, errors = parse_question_file(uploaded_file)
    except ValueError as exc:
        return Response(
            {"error": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if errors:
        return Response(
            {
                "message": "Import rejected. Fix the invalid rows and retry.",
                "imported_count": 0,
                "errors": errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        questions = [
            Question(**question_data)
            for question_data in validated_questions
        ]
        created_questions = Question.objects.bulk_create(questions)

    return Response(
        {
            "message": "Questions imported successfully.",
            "imported_count": len(created_questions),
            "question_ids": [question.id for question in created_questions],
        },
        status=status.HTTP_201_CREATED,
    )


class QuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = QuestionSerializer
    queryset = Question.objects.all()
    permission_classes = [IsFacultyOrAdmin]

    def _is_locked(self, question):
        return question.exams.filter(
            status__in=["PUBLISHED", "LIVE"]
        ).exists()

    def update(self, request, *args, **kwargs):
        question = self.get_object()

        if self._is_locked(question):
            return Response(
                {
                    "detail": (
                        "This question cannot be edited because it is "
                        "attached to a published or live exam."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        question = self.get_object()

        if self._is_locked(question):
            return Response(
                {
                    "detail": (
                        "This question cannot be deleted because it is "
                        "attached to a published or live exam."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Remove links only from draft exams before deleting the question.
        question.exam_question_links.filter(
            exam__status="DRAFT"
        ).delete()

        question.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
