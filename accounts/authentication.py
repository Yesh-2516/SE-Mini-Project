from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed

# Avoid a database write on every request; activity only needs minute accuracy.
ACTIVITY_WRITE_INTERVAL = timedelta(seconds=60)


def last_activity(user, token):
    if user.last_activity_at is None:
        return token.created
    return max(user.last_activity_at, token.created)


def is_idle_expired(user, token, now=None):
    now = now or timezone.now()
    return now - last_activity(user, token) >= settings.TOKEN_IDLE_TIMEOUT


def touch_activity(user, now):
    user.last_activity_at = now
    type(user).objects.filter(pk=user.pk).update(last_activity_at=now)


def issue_token(user, now=None):
    """Return the user's token, replacing one that has gone idle (OEP-SR-003)."""
    now = now or timezone.now()

    # Without this, logging in would revive a token that had already expired.
    stale = Token.objects.filter(user=user).first()
    if stale is not None and is_idle_expired(user, stale, now):
        stale.delete()

    token, _ = Token.objects.get_or_create(user=user)
    touch_activity(user, now)
    return token


class IdleExpiringTokenAuthentication(TokenAuthentication):
    """Reject tokens unused for ``TOKEN_IDLE_TIMEOUT`` (OEP-SR-003)."""

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        now = timezone.now()

        if is_idle_expired(user, token, now):
            token.delete()
            raise AuthenticationFailed("Session expired. Please log in again.")

        if now - last_activity(user, token) >= ACTIVITY_WRITE_INTERVAL:
            touch_activity(user, now)

        return user, token
