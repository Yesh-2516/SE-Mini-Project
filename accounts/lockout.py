from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.audit import client_ip, record_audit_event


def is_locked(user, now=None):
    """Return True while the account's temporary lock is running."""
    now = now or timezone.now()
    return user.locked_until is not None and user.locked_until > now


@transaction.atomic
def record_failed_login(user, request=None, now=None):
    """Count a failed login and lock the account at the threshold (OEP-F-004)."""
    now = now or timezone.now()

    # Lock the row so parallel guesses cannot lose a count.
    account = type(user).objects.select_for_update().get(pk=user.pk)
    if is_locked(account, now):
        return

    account.failed_login_attempts += 1

    if account.failed_login_attempts >= settings.ACCOUNT_LOCKOUT_THRESHOLD:
        account.failed_login_attempts = 0
        account.locked_until = now + settings.ACCOUNT_LOCKOUT_DURATION
        record_audit_event(
            "account.locked",
            actor=account,
            description="Account locked after consecutive failed logins",
            metadata={
                "target_user_id": account.pk,
                "locked_until": account.locked_until.isoformat(),
            },
            ip_address=client_ip(request),
        )

    account.save(update_fields=["failed_login_attempts", "locked_until"])


def clear_failed_logins(user):
    """Reset the counter after a successful login."""
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until"])
