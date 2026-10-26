from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import (
    DUPLICATE,
    PASSWORD_POLICY,
    StudentRegistrationSerializer,
    UserSerializer,
)


def validation_error_status(errors):
    """Map serializer errors to 400, 409 (duplicate) or 422 (password policy)."""

    codes = {
        getattr(detail, "code", None)
        for details in errors.values()
        for detail in details
    }

    if codes - {DUPLICATE, PASSWORD_POLICY}:
        return status.HTTP_400_BAD_REQUEST
    if DUPLICATE in codes:
        return status.HTTP_409_CONFLICT
    return status.HTTP_422_UNPROCESSABLE_ENTITY


# Mask passwords in Django error reports (OEP-SR-002).
@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class StudentRegistrationView(APIView):
    """Let a new student create an account."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = StudentRegistrationSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=validation_error_status(serializer.errors),
            )

        try:
            with transaction.atomic():
                user = serializer.save()
        except IntegrityError:
            # A concurrent sign-up claimed the same email or roll number.
            return Response(
                {"detail": "An account with these details already exists."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )
