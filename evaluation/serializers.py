from decimal import Decimal

from rest_framework import serializers


class EvaluateResponseSerializer(serializers.Serializer):
    # The upper bound depends on the exam question, so the service checks it.
    marks = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=Decimal("0"),
    )
    feedback = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=5000,
    )
