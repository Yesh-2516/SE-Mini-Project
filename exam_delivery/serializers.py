from rest_framework import serializers


class AutosaveItemSerializer(serializers.Serializer):
    question_id = serializers.IntegerField(required=True)
    submitted_answer = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    answer = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    is_flagged = serializers.BooleanField(required=False, allow_null=True)


class AutosaveRequestSerializer(serializers.Serializer):
    responses = serializers.ListField(
        child=AutosaveItemSerializer(),
        required=True,
        allow_empty=True,
    )


class SubmitRequestSerializer(serializers.Serializer):
    responses = serializers.ListField(
        child=AutosaveItemSerializer(),
        required=False,
        allow_empty=True,
    )
    reason = serializers.ChoiceField(
        choices=["manual", "timeout"],
        default="manual",
    )


class FlagToggleSerializer(serializers.Serializer):
    is_flagged = serializers.BooleanField(required=False, allow_null=True)
