from django.conf import settings

from accounts.audit_models import AuditLog

# The four action types OEP-NF-004 requires. Logins are recorded as
# "login.success" (plus "account.locked" for lockouts, see accounts.lockout).
EVENT_LOGIN = "login.success"
EVENT_SUBMISSION = "exam.submitted"
EVENT_EVALUATION = "evaluation.updated"
EVENT_INTEGRITY_FLAG = "integrity.flag"


def client_ip(request):
    """The client's IP address, for audit records.

    Behind the nginx proxy (DJANGO_TLS_ENABLED on) REMOTE_ADDR is always the
    proxy, so the address comes from X-Forwarded-For. nginx appends the
    address it saw to whatever the client sent, so only the last entry can
    be trusted. Without the proxy the header is ignored, because any client
    could set it.
    """
    if request is None:
        return None
    if settings.TLS_ENABLED:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        last_hop = forwarded.split(",")[-1].strip()
        if last_hop:
            return last_hop
    return request.META.get("REMOTE_ADDR")


def record_audit_event(
    event_type,
    actor=None,
    description="",
    metadata=None,
    ip_address=None,
):
    """Record a security or administrative event without secrets.

    Never put passwords, tokens or answer content in ``metadata``: only IDs,
    scores and other facts needed to follow what happened.
    """
    return AuditLog.objects.create(
        actor=actor,
        event_type=event_type,
        description=description,
        metadata=metadata or {},
        ip_address=ip_address,
    )


def record_integrity_flag(actor, reason, **details):
    """Log a suspicious action as an integrity flag (OEP-NF-004, OEP-F-062)."""
    return record_audit_event(
        EVENT_INTEGRITY_FLAG,
        actor=actor,
        description=f"Integrity flag: {reason}",
        metadata={"reason": reason, **details},
    )
