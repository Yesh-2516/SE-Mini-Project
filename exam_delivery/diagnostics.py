"""Server health and database connectivity checks (OEP-F-063, TC-Admin-04).

Shared by the admin API (/api/admin/diagnostics/) and the admin health panel
in the website, so both always report the same thing.
"""
import logging
import platform
import sys
import time

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone

from exam_delivery.models import Attempt
from exam_management.models import Exam

logger = logging.getLogger(__name__)


def collect_diagnostics():
    """Check the server and database. Never raises and never exposes errors."""

    User = get_user_model()
    db_status = "connected"
    db_latency_ms = None
    metrics = {
        "active_attempts": None,
        "total_exams": None,
        "total_users": None,
    }
    errors = []

    # Connectivity and metrics are guarded independently so one failed
    # query cannot turn a degraded health response into an HTTP 500.
    try:
        started = time.perf_counter()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        db_latency_ms = round((time.perf_counter() - started) * 1000, 2)
        if not row or row[0] != 1:
            raise RuntimeError("Database connectivity probe returned an unexpected result.")
    except Exception:
        db_status = "unreachable"
        errors.append("connectivity")
        logger.exception("Admin diagnostics database connectivity check failed")

    metric_queries = {
        "active_attempts": lambda: Attempt.objects.filter(
            status=Attempt.Status.IN_PROGRESS
        ).count(),
        "total_exams": lambda: Exam.objects.count(),
        "total_users": lambda: User.objects.count(),
    }
    for metric_name, query in metric_queries.items():
        try:
            metrics[metric_name] = query()
        except Exception:
            if db_status != "unreachable":
                db_status = "degraded"
            errors.append(metric_name)
            logger.exception("Admin diagnostics metric query failed: %s", metric_name)

    healthy = db_status == "connected" and not errors
    return {
        "status": "healthy" if healthy else "degraded",
        "timestamp": timezone.now().isoformat(),
        "server": {
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
            "django_version": django.get_version(),
            "status": "operational",
        },
        "database": {
            "status": db_status,
            "engine": settings.DATABASES["default"]["ENGINE"],
            "latency_ms": db_latency_ms,
        },
        "metrics": metrics,
    }
