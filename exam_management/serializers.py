from rest_framework import serializers

from exam_management.models import Exam


class ExamCreateSerializer(serializers.ModelSerializer):
    """Validate and serialize exam details and scoring settings."""

    total_marks = serializers.IntegerField(read_only=True)

    class Meta:
        model = Exam
        fields = [
            "id",
            "title",
            "status",
            "duration_minutes",
            "negative_marking_enabled",
            "negative_marks",
            "total_marks",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "total_marks",
            "created_at",
            "updated_at",
        ]

    def validate_duration_minutes(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Duration must be greater than zero minutes."
            )
        return value

    def validate_negative_marks(self, value):
        if value < 0:
            raise serializers.ValidationError(
                "Negative marks cannot be less than zero."
            )
        return value

    def validate(self, attrs):
        enabled = attrs.get(
            "negative_marking_enabled",
            getattr(self.instance, "negative_marking_enabled", False),
        )
        penalty = attrs.get(
            "negative_marks",
            getattr(self.instance, "negative_marks", 0),
        )

        if enabled and penalty <= 0:
            raise serializers.ValidationError({
                "negative_marks": (
                    "Set a penalty greater than zero when negative marking is enabled."
                )
            })

        return attrs


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


class ExamQuestionMarksSerializer(serializers.Serializer):
    """Validate the marks assigned to a question in an exam."""

    question_id = serializers.IntegerField(min_value=1)
    marks = serializers.IntegerField(min_value=1)
