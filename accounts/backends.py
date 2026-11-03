from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from accounts.lockout import clear_failed_logins, is_locked, record_failed_login
from accounts.models import normalize_email, normalize_roll_number


def find_account(identifier):
    """Return the user matching a username, email address or roll number."""
    UserModel = get_user_model()
    identifier = identifier.strip()

    return (
        UserModel._default_manager.filter(username=identifier).first()
        or UserModel._default_manager.filter(
            email=normalize_email(identifier)
        ).first()
        or UserModel._default_manager.filter(
            roll_number=normalize_roll_number(identifier)
        ).first()
    )


class EmailUsernameOrRollNumberBackend(ModelBackend):
    """Authenticate with a username, email address or roll number.

    Lockout lives here rather than in the login view so that every login
    path, including the Django admin site, is covered (OEP-F-004).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()

        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None

        user = find_account(username)

        if user is None:
            # Run the hasher anyway so unknown accounts take as long as
            # known ones (same mitigation as ModelBackend).
            UserModel().set_password(password)
            return None

        if is_locked(user) or not self.user_can_authenticate(user):
            return None

        if user.check_password(password):
            clear_failed_logins(user)
            return user

        record_failed_login(user, request)
        return None
