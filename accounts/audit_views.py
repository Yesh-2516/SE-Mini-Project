from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit_models import AuditLog
from accounts.permissions import IsAdmin


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "event_type",
            "description",
            "metadata",
            "ip_address",
            "created_at",
        ]


class AuditLogListView(APIView):
    """Allow administrators to review recent audit events."""

    permission_classes = [IsAdmin]

    def get(self, request):
        logs = AuditLog.objects.select_related("actor").order_by(
            "-created_at"
        )[:100]
        return Response(AuditLogSerializer(logs, many=True).data)
