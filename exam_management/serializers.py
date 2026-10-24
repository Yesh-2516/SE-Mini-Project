
from rest_framework import serializers

from exam_management.models import Exam


class ExamCreateSerializer(serializers.ModelSerializer):
    """Validate the data needed to create a draft exam."""

    class Meta:
        model = Exam
        fields = ["id", "title", "status", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "created_at", "updated_at"]


class ManualAssemblySerializer(serializers.Serializer):
    """Validate a manually selected, ordered list of question IDs."""

    question_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class RuleGenerationSerializer(serializers.Serializer):
    """Validate rules for generating an exam from the question bank."""

    subject = serializers.CharField(
        max_length=200,
        allow_blank=False,
        trim_whitespace=True,
    )
    topic = serializers.CharField(
        max_length=200,
        allow_blank=False,
        trim_whitespace=True,
    )
    difficulty_counts = serializers.DictField(
        child=serializers.IntegerField(min_value=0),
        allow_empty=False,
    )
