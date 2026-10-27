from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from accounts.models import User, normalize_email, normalize_roll_number

# Error codes the views map to HTTP statuses (409 / 422).
DUPLICATE = "duplicate"
PASSWORD_POLICY = "password_policy"


def check_unique_identity(*, email, roll_number, username, exclude_pk=None):
    """Raise a 'duplicate' error if the email, roll number or username is taken."""

    users = User.objects.all()
    if exclude_pk is not None:
        users = users.exclude(pk=exclude_pk)

    errors = {}

    if email and users.filter(email=email).exists():
        errors["email"] = "An account with this email already exists."

    if roll_number and users.filter(roll_number=roll_number).exists():
        errors["roll_number"] = (
            "An account with this roll number already exists."
        )

    if (
        username
        and "email" not in errors
        and "roll_number" not in errors
        and users.filter(
            Q(username=username) | Q(email=username) | Q(roll_number=username)
        ).exists()
    ):
        errors["username"] = "An account with this username already exists."

    if errors:
        raise serializers.ValidationError(
            {
                field: [serializers.ErrorDetail(message, code=DUPLICATE)]
                for field, message in errors.items()
            }
        )


def check_password_policy(password, user):
    """Raise a 'password_policy' error if the password breaks the policy."""

    try:
        validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({
            "password": [
                serializers.ErrorDetail(message, code=PASSWORD_POLICY)
                for message in exc.messages
            ]
        }) from None


class StudentRegistrationSerializer(serializers.Serializer):
    """Validate a self-service student sign-up."""

    first_name = serializers.CharField(max_length=150, trim_whitespace=True)
    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    roll_number = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
    )
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        email = normalize_email(attrs.get("email"))
        roll_number = normalize_roll_number(attrs.get("roll_number"))

        if not email and not roll_number:
            raise serializers.ValidationError({
                "non_field_errors": [
                    "Provide an institutional email or a roll number."
                ]
            })

        username = email or roll_number.lower()

        check_unique_identity(
            email=email,
            roll_number=roll_number,
            username=username,
        )

        candidate = User(
            username=username,
            email=email,
            roll_number=roll_number,
            first_name=attrs["first_name"],
            last_name=attrs.get("last_name", ""),
        )
        check_password_policy(attrs["password"], candidate)

        attrs["email"] = email
        attrs["roll_number"] = roll_number
        attrs["username"] = username
        return attrs

    def create(self, validated_data):
        # Role is fixed: public sign-up can only ever create students.
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data["first_name"],
            last_name=validated_data.get("last_name", ""),
            roll_number=validated_data["roll_number"],
            role=User.Role.STUDENT,
        )


class UserSerializer(serializers.ModelSerializer):
    """Public, read-only view of an account."""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "roll_number",
            "first_name",
            "last_name",
            "role",
        ]
        read_only_fields = fields


class LoginSerializer(serializers.Serializer):
    """Accept a username, email or roll number together with a password."""

    username = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        identifier = (attrs.get("username") or attrs.get("email") or "").strip()

        if not identifier:
            raise serializers.ValidationError({
                "username": ["Provide a username, email or roll number."]
            })

        attrs["identifier"] = identifier
        return attrs


MANAGED_ROLES = (User.Role.FACULTY, User.Role.STUDENT)


class ManagedAccountSerializer(serializers.ModelSerializer):
    """Faculty/Student account as created and edited by an Admin."""

    username = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
        validators=[UnicodeUsernameValidator()],
    )
    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    roll_number = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    role = serializers.ChoiceField(
        choices=[(role.value, role.label) for role in MANAGED_ROLES],
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "roll_number",
            "first_name",
            "last_name",
            "role",
            "is_active",
            "password",
            "date_joined",
            "last_login",
        ]
        read_only_fields = ["id", "is_active", "date_joined", "last_login"]

    def _current(self, attrs, field):
        if field in attrs:
            return attrs[field]
        return getattr(self.instance, field, None)

    def validate(self, attrs):
        email = normalize_email(self._current(attrs, "email"))
        roll_number = normalize_roll_number(self._current(attrs, "roll_number"))

        if not email and not roll_number:
            raise serializers.ValidationError({
                "non_field_errors": ["Provide an email or a roll number."]
            })

        username = (self._current(attrs, "username") or "").strip()
        if not username:
            username = email or roll_number.lower()

        password = attrs.get("password")
        if self.instance is None and not password:
            raise serializers.ValidationError({
                "password": ["A password is required for new accounts."]
            })

        check_unique_identity(
            email=email,
            roll_number=roll_number,
            username=username,
            exclude_pk=getattr(self.instance, "pk", None),
        )

        if password:
            candidate = User(
                username=username,
                email=email,
                roll_number=roll_number,
                first_name=self._current(attrs, "first_name") or "",
                last_name=self._current(attrs, "last_name") or "",
            )
            check_password_policy(password, candidate)

        attrs["email"] = email
        attrs["roll_number"] = roll_number
        attrs["username"] = username
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        instance.save()

        if password:
            # A reset password signs the account out everywhere.
            Token.objects.filter(user=instance).delete()

        return instance
