from django.conf import settings

from accounts.audit_models import AuditLog


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
    """Record a security or administrative event without secrets."""
    return AuditLog.objects.create(
        actor=actor,
        event_type=event_type,
        description=description,
        metadata=metadata or {},
        ip_address=ip_address,
    )
