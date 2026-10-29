from django.conf import settings
from django.db import models


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

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Audit log"
        verbose_name_plural = "Audit logs"

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"
