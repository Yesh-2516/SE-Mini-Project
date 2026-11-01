from django.contrib.auth import authenticate, user_logged_in
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.permissions import IsAdmin
from accounts.serializers import (
    DUPLICATE,
    MANAGED_ROLES,
    PASSWORD_POLICY,
    LoginSerializer,
    ManagedAccountSerializer,
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


def save_account(serializer, output_serializer_class, success_status):
    """Save a validated account serializer, mapping a uniqueness race to 409."""

    try:
        with transaction.atomic():
            user = serializer.save()
    except IntegrityError:
        # A concurrent request claimed the same email, roll number or username.
        return Response(
            {"detail": "An account with these details already exists."},
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        output_serializer_class(user).data,
        status=success_status,
    )


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

        return save_account(
            serializer,
            UserSerializer,
            status.HTTP_201_CREATED,
        )


@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class LoginView(APIView):
    """Check credentials against the stored hash and issue an API token."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request._request,
            username=serializer.validated_data["identifier"],
            password=serializer.validated_data["password"],
        )

        if user is None:
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token, _ = Token.objects.get_or_create(user=user)
        user_logged_in.send(
            sender=user.__class__,
            request=request._request,
            user=user,
        )

        from accounts.audit import record_audit_event
        record_audit_event(
            "login.success",
            actor=user,
            description="User logged in successfully",
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response({
            "token": token.key,
            "role": user.role,
            "user": UserSerializer(user).data,
        })


class LogoutView(APIView):
    """Invalidate the caller's API token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentUserView(APIView):
    """Return the logged-in user so the client can open the role dashboard."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ManagedAccountMixin:
    """Admin-only access to Faculty and Student accounts."""

    permission_classes = [IsAdmin]
    serializer_class = ManagedAccountSerializer

    def get_queryset(self):
        queryset = User.objects.filter(role__in=MANAGED_ROLES).order_by("username")

        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(role=role.strip().upper())

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    def validate_and_save(self, serializer, success_status):
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=validation_error_status(serializer.errors),
            )
        return save_account(serializer, ManagedAccountSerializer, success_status)


@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class ManagedAccountListCreateView(ManagedAccountMixin, generics.ListCreateAPIView):
    """List or create Faculty and Student accounts."""

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        response = self.validate_and_save(
            serializer, status.HTTP_201_CREATED
        )
        if response.status_code == status.HTTP_201_CREATED:
            from accounts.audit import record_audit_event
            record_audit_event(
                "account.created",
                actor=request.user,
                description="Admin created an account",
                metadata={"role": response.data.get("role", "")},
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        return response


@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class ManagedAccountDetailView(ManagedAccountMixin, generics.RetrieveUpdateAPIView):
    """Retrieve or edit a Faculty or Student account."""

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            self.get_object(),
            data=request.data,
            partial=kwargs.get("partial", False),
        )
        response = self.validate_and_save(
            serializer, status.HTTP_200_OK
        )
        if response.status_code == status.HTTP_200_OK:
            from accounts.audit import record_audit_event
            record_audit_event(
                "account.updated",
                actor=request.user,
                description="Admin updated an account",
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        return response


class SetAccountActiveView(ManagedAccountMixin, APIView):
    """Deactivate or reactivate an account; deactivation signs it out."""

    is_active = None

    def post(self, request, pk):
        user = get_object_or_404(self.get_queryset(), pk=pk)

        user.is_active = self.is_active
        user.save(update_fields=["is_active"])

        if not self.is_active:
            Token.objects.filter(user=user).delete()

        from accounts.audit import record_audit_event
        record_audit_event(
            "account.activated" if self.is_active else "account.deactivated",
            actor=request.user,
            description="Admin changed account active status",
            metadata={
                "target_user_id": user.pk,
                "is_active": self.is_active,
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(ManagedAccountSerializer(user).data)
