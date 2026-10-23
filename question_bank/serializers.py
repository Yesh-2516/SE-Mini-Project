
from rest_framework import serializers

from question_bank.models import Question


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = [
            "id",
            "text",
            "question_type",
            "options",
            "correct_answer",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_text(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Question text cannot be blank."
            )
        return value

    def validate(self, attrs):
        question_type = attrs.get(
            "question_type",
            getattr(self.instance, "question_type", None),
        )
        options = attrs.get(
            "options",
            getattr(self.instance, "options", []),
        )
        correct_answer = attrs.get(
            "correct_answer",
            getattr(self.instance, "correct_answer", ""),
        )

        if question_type == Question.QuestionType.MCQ:
            if not isinstance(options, list) or len(options) < 2:
                raise serializers.ValidationError({
                    "options": "MCQs must have at least two options."
                })

            if any(
                not isinstance(option, str) or not option.strip()
                for option in options
            ):
                raise serializers.ValidationError({
                    "options": "Each option must be a non-empty string."
                })

            normalized_options = [
                option.strip().casefold() for option in options
            ]

            if len(set(normalized_options)) != len(options):
                raise serializers.ValidationError({
                    "options": "MCQ options must be unique."
                })

            if (
                not isinstance(correct_answer, str)
                or correct_answer.strip().casefold()
                not in normalized_options
            ):
                raise serializers.ValidationError({
                    "correct_answer": (
                        "The correct answer must match one of the options."
                    )
                })

        elif question_type == Question.QuestionType.TRUE_FALSE:
            if correct_answer not in ["True", "False"]:
                raise serializers.ValidationError({
                    "correct_answer": "The answer must be 'True' or 'False'."
                })

        elif question_type == Question.QuestionType.SHORT_ANSWER:
            if not isinstance(correct_answer, str) or not correct_answer.strip():
                raise serializers.ValidationError({
                    "correct_answer": "A correct answer is required."
                })

        return attrs
