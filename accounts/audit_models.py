from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# OEP-NF-004: entries must be kept for at least one academic year. The
# configured retention may be longer, never shorter.
MINIMUM_RETENTION_DAYS = 365


class AuditLogImmutable(Exception):
    """Raised when code tries to change or delete a stored audit entry."""


def retention_days():
    """Days an entry is kept (AUDIT_LOG_RETENTION_DAYS, at least a year)."""
    configured = getattr(settings, "AUDIT_LOG_RETENTION_DAYS", MINIMUM_RETENTION_DAYS)
    return max(MINIMUM_RETENTION_DAYS, int(configured))


def retention_cutoff(now=None):
    """Entries created before this moment are past their retention period."""
    return (now or timezone.now()) - timedelta(days=retention_days())


class AuditLogQuerySet(models.QuerySet):
    """Append-only: rows can be added and read, never edited or removed.

    The one exception is ``purge_expired``, which only removes entries that
    are already past the retention period (OEP-NF-004).
    """

    def update(self, **kwargs):
        raise AuditLogImmutable("Audit log entries cannot be updated.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise AuditLogImmutable("Audit log entries cannot be updated.")

    def delete(self):
        raise AuditLogImmutable("Audit log entries cannot be deleted.")

    def purge_expired(self, cutoff=None):
        """Delete entries older than the retention period; return the count.

        A cutoff newer than the retention period is refused, so a caller can
        never shorten the retention below the configured minimum.
        """
        floor = retention_cutoff()
        cutoff = floor if cutoff is None else cutoff
        if cutoff > floor:
            raise ValueError(
                "Audit entries cannot be purged before the retention period "
                f"of {retention_days()} days has passed."
            )
        expired = self.filter(created_at__lt=cutoff)
        deleted, _ = super(AuditLogQuerySet, expired).delete()
        return deleted


class AuditLog(models.Model):
    """Record security and administrative events."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    event_type = models.CharField(max_length=100, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit log"
        verbose_name_plural = "Audit logs"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditLogImmutable("Audit log entries cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditLogImmutable("Audit log entries cannot be deleted.")

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"
