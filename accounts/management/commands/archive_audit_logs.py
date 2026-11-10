"""Archive audit-log entries that are past their retention period (OEP-NF-004).

Entries younger than the retention period (at least one academic year, see
``AUDIT_LOG_RETENTION_DAYS``) are never touched. Older entries are written to
a JSON Lines file first; they are removed from the database only after the
file has been written and its line count verified.

Run it on a schedule, e.g. a weekly cron job:

    python manage.py archive_audit_logs --archive-dir /var/archive/audit
"""

import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.audit import record_audit_event
from accounts.audit_models import AuditLog, retention_cutoff, retention_days


def entry_to_dict(entry):
    return {
        "id": entry.id,
        "actor_id": entry.actor_id,
        "event_type": entry.event_type,
        "description": entry.description,
        "metadata": entry.metadata,
        "ip_address": entry.ip_address,
        "created_at": entry.created_at.isoformat(),
    }


class Command(BaseCommand):
    help = (
        "Write audit-log entries older than the retention period to a "
        "JSON Lines archive file, then remove them from the database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--archive-dir",
            default="audit_archive",
            help="Directory for the archive file (default: audit_archive).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be archived without writing or deleting.",
        )

    def handle(self, *args, **options):
        cutoff = retention_cutoff()
        expired = AuditLog.objects.filter(created_at__lt=cutoff)
        count = expired.count()

        self.stdout.write(
            f"Retention: {retention_days()} days. "
            f"{count} entries are past it (created before {cutoff.isoformat()})."
        )
        if count == 0 or options["dry_run"]:
            return

        archive_dir = Path(options["archive_dir"])
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"audit-archive-{timezone.now():%Y%m%dT%H%M%S}.jsonl"

        written = 0
        with archive_path.open("w", encoding="utf-8") as handle:
            for entry in expired.order_by("created_at", "id").iterator():
                handle.write(json.dumps(entry_to_dict(entry)) + "\n")
                written += 1
            handle.flush()
            os.fsync(handle.fileno())

        with archive_path.open("r", encoding="utf-8") as handle:
            verified = sum(1 for _ in handle)
        if verified != written:
            raise CommandError(
                f"Archive check failed ({verified} of {written} lines); "
                "nothing was deleted."
            )

        removed = AuditLog.objects.purge_expired(cutoff)
        record_audit_event(
            "audit.archived",
            description="Expired audit entries archived",
            metadata={"file": archive_path.name, "entries": written},
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Archived {written} entries to {archive_path} and removed {removed}."
            )
        )
