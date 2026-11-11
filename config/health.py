"""Public liveness check for uptime monitoring (OEP-NF-003, TC-Ops-01).

Monitors poll this without logging in, so it reveals nothing beyond up or
down. Admins get the detailed view from the diagnostics panel (OEP-F-063).
"""
import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@never_cache
@require_safe
def health(request):
    """Return 200 when the app can reach its database, otherwise 503."""

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        if not row or row[0] != 1:
            raise RuntimeError("Database probe returned an unexpected result.")
    except Exception:
        logger.exception("Health check could not reach the database")
        return JsonResponse({"status": "unavailable"}, status=503)

    return JsonResponse({"status": "ok"})
