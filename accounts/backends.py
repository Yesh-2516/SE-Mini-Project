from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from accounts.models import normalize_email, normalize_roll_number


class EmailUsernameOrRollNumberBackend(ModelBackend):
    """Authenticate with a username, email address or roll number."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()

        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None

        identifier = username.strip()
        user = (
            UserModel._default_manager.filter(username=identifier).first()
            or UserModel._default_manager.filter(
                email=normalize_email(identifier)
            ).first()
            or UserModel._default_manager.filter(
                roll_number=normalize_roll_number(identifier)
            ).first()
        )

        if user is None:
            # Run the hasher anyway so unknown accounts take as long as
            # known ones (same mitigation as ModelBackend).
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
