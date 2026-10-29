from accounts.audit_models import AuditLog


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
