from rest_framework import serializers

from exam_management.models import Exam, StudentAnswer
from question_bank.models import Question


class ExamCreateSerializer(serializers.ModelSerializer):
    """Validate and serialize exam details and scoring settings."""

    total_marks = serializers.IntegerField(read_only=True)

    class Meta:
        model = Exam
        fields = [
            "id",
            "title",
            "course",
            "status",
            "duration_minutes",
            "availability_start",
            "availability_end",
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

        availability_start = attrs.get(
            "availability_start",
            getattr(self.instance, "availability_start", None),
        )
        availability_end = attrs.get(
            "availability_end",
            getattr(self.instance, "availability_end", None),
        )

        if (availability_start is None) != (availability_end is None):
            raise serializers.ValidationError({
                "availability": (
                    "Both availability start and end must be provided together."
                )
            })

        if (
            availability_start is not None
            and availability_end is not None
            and availability_end <= availability_start
        ):
            raise serializers.ValidationError({
                "availability_end": (
                    "Availability end must be later than availability start."
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


class StudentExamQuestionSerializer(serializers.Serializer):
    """Question as shown to a student taking an exam (OEP-SR-004).

    Fields are listed explicitly so new Question fields, such as the
    correct answer, can never reach a student by default.
    """

    question_id = serializers.IntegerField(source="question.id")
    position = serializers.IntegerField()
    marks = serializers.IntegerField()
    text = serializers.CharField(source="question.text")
    question_type = serializers.CharField(source="question.question_type")
    options = serializers.SerializerMethodField()

    def get_options(self, exam_question):
        question = exam_question.question

        if question.question_type == Question.QuestionType.MCQ:
            return list(question.options)
        if question.question_type == Question.QuestionType.TRUE_FALSE:
            return ["True", "False"]
        # Free-text answers get no options, so nothing stored there leaks.
        return []


class ExamQuestionMarksSerializer(serializers.Serializer):
    """Validate the marks assigned to a question in an exam."""

    question_id = serializers.IntegerField(min_value=1)
    marks = serializers.IntegerField(min_value=1)

class FacultyPendingAnswerSerializer(serializers.ModelSerializer):
    student_id = serializers.IntegerField(read_only=True)
    question_text = serializers.CharField(
        source="question.text",
        read_only=True
    )
    question_type = serializers.CharField(
        source="question.question_type",
        read_only=True
    )

    class Meta:


        model = StudentAnswer
        fields = [
            "id",
            "student_id",
            "exam_id",
            "question_id",
            "question_text",
            "question_type",
            "submitted_answer",
            "submitted_at",
        ]


class GradeSubjectiveAnswerSerializer(serializers.Serializer):
    marks_awarded = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=0
    )
    feedback = serializers.CharField(
        required=False,
        allow_blank=True
    )
