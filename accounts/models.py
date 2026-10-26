from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        return super().create_superuser(
            username,
            email,
            password,
            **extra_fields,
        )


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        FACULTY = "FACULTY", "Faculty"
        STUDENT = "STUDENT", "Student"

    # Stored lowercase; NULL (not "") when absent so uniqueness ignores it.
    email = models.EmailField(unique=True, null=True, blank=True)
    # Stored uppercase; NULL when absent so uniqueness ignores it.
    roll_number = models.CharField(
        max_length=30,
        unique=True,
        null=True,
        blank=True,
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STUDENT,
    )

    objects = UserManager()

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        self.roll_number = normalize_roll_number(self.roll_number)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


def normalize_email(value):
    if value is None or not value.strip():
        return None
    return value.strip().lower()


def normalize_roll_number(value):
    if value is None or not value.strip():
        return None
    return value.strip().upper()
