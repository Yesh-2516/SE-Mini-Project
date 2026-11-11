from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.audit_models import AuditLog
from accounts.permissions import IsAdmin

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


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


def _whole_number(params, name, default, minimum, maximum=None):
    raw = params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValidationError({name: "Must be a whole number."})
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum} and {maximum}" if maximum else f"at least {minimum}"
        raise ValidationError({name: f"Must be {bound}."})
    return value


def _moment(params, name, end_of_day=False):
    raw = params.get(name)
    if raw is None:
        return None
    try:
        moment = parse_datetime(raw)
        if moment is None:
            day = parse_date(raw)
            if day is None:
                raise ValueError
            moment = datetime.combine(day, time.max if end_of_day else time.min)
    except ValueError:
        raise ValidationError({name: "Use an ISO date (2026-11-09) or date-time."})
    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return moment


class AuditLogListView(APIView):
    """Let administrators retrieve audit events (OEP-F-062, OEP-NF-004).

    Optional filters: ``event_type``, ``actor`` (user id), ``since`` and
    ``until`` (ISO date or date-time), ``limit`` (default 100, at most 500) and
    ``offset``. Newest entries come first.
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        params = request.query_params
        logs = AuditLog.objects.select_related("actor")

        event_type = params.get("event_type")
        if event_type:
            logs = logs.filter(event_type=event_type)

        actor = _whole_number(params, "actor", None, 1)
        if actor is not None:
            logs = logs.filter(actor_id=actor)

        since = _moment(params, "since")
        if since is not None:
            logs = logs.filter(created_at__gte=since)
        until = _moment(params, "until", end_of_day=True)
        if until is not None:
            logs = logs.filter(created_at__lte=until)

        limit = _whole_number(params, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _whole_number(params, "offset", 0, 0)

        logs = logs.order_by("-created_at", "-id")[offset:offset + limit]
        return Response(AuditLogSerializer(logs, many=True).data)
