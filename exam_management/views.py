
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from exam_management.models import Exam, ExamQuestion
from exam_management.serializers import (
    ExamCreateSerializer,
    ExamQuestionMarksSerializer,
    ManualAssemblySerializer,
    RuleGenerationSerializer,
)
from exam_management.services import (
    assemble_exam_manually,
    generate_exam_by_rules,
)
from rest_framework.exceptions import ValidationError


class ExamListCreateView(generics.ListCreateAPIView):
    """List exams or create a new draft exam."""

    queryset = Exam.objects.all().order_by("-created_at")
    serializer_class = ExamCreateSerializer
    permission_classes = [IsAdminUser]


class ExamDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve an exam and its ordered question list."""

    queryset = Exam.objects.prefetch_related(
        "exam_questions__question"
    )
    serializer_class = ExamCreateSerializer
    permission_classes = [IsAdminUser]

    def retrieve(self, request, *args, **kwargs):
        exam = self.get_object()

        questions = [
            {
                "id": item.question_id,
                "position": item.position,
                "text": item.question.text,
                "question_type": item.question.question_type,
                "subject": item.question.subject,
                "topic": item.question.topic,
                "difficulty": item.question.difficulty,
                "marks": item.marks,
            }
            for item in exam.exam_questions.all()
        ]

        data = self.get_serializer(exam).data
        data["questions"] = questions

        return Response(data)

    def perform_update(self, serializer):
        if serializer.instance.status != Exam.Status.DRAFT:
            raise ValidationError(
                "Only draft exams can have their settings updated."
            )

        serializer.save()

class ManualAssemblyView(APIView):
    """Assemble an exam from manually selected question IDs."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        exam = get_object_or_404(Exam, pk=pk)
        serializer = ManualAssemblySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assemble_exam_manually(
            exam=exam,
            question_ids=serializer.validated_data["question_ids"],
        )

        return Response(
            {"detail": "Exam questions assembled successfully."},
            status=status.HTTP_200_OK,
        )


class RuleGenerationView(APIView):
    """Generate an exam from subject, topic and difficulty counts."""

    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        exam = get_object_or_404(Exam, pk=pk)
        serializer = RuleGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        generate_exam_by_rules(
            exam=exam,
            subject=serializer.validated_data["subject"],
            topic=serializer.validated_data["topic"],
            difficulty_counts=serializer.validated_data["difficulty_counts"],
        )

        return Response(
            {"detail": "Exam questions generated successfully."},
            status=status.HTTP_200_OK,
        )

class ExamQuestionMarksView(APIView):
    """Update the marks assigned to a question in an exam."""

    permission_classes = [IsAdminUser]

    def patch(self, request, pk, question_id):
        exam = get_object_or_404(Exam, pk=pk)

        if exam.status != Exam.Status.DRAFT:
            raise ValidationError(
                "Only draft exams can have their question marks updated."
            )

        serializer = ExamQuestionMarksSerializer(data={
            "question_id": question_id,
            "marks": request.data.get("marks"),
        })
        serializer.is_valid(raise_exception=True)

        exam_question = get_object_or_404(
            ExamQuestion,
            exam=exam,
            question_id=serializer.validated_data["question_id"],
        )

        exam_question.marks = serializer.validated_data["marks"]
        exam_question.save(update_fields=["marks"])

        return Response({
            "detail": "Question marks updated successfully.",
            "question_id": exam_question.question_id,
            "marks": exam_question.marks,
            "total_marks": exam.total_marks,
        })