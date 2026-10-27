from rest_framework.permissions import BasePermission

from accounts.models import User


class HasRole(BasePermission):
    """Allow active, authenticated users whose role is in ``allowed_roles``."""

    allowed_roles = ()
    message = "Your role is not allowed to perform this action."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, "role", None) in self.allowed_roles
        )


class IsAdmin(HasRole):
    allowed_roles = (User.Role.ADMIN,)


class IsFaculty(HasRole):
    allowed_roles = (User.Role.FACULTY,)


class IsStudent(HasRole):
    allowed_roles = (User.Role.STUDENT,)


class IsFacultyOrAdmin(HasRole):
    allowed_roles = (User.Role.FACULTY, User.Role.ADMIN)
