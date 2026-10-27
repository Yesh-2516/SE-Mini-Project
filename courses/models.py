from django.conf import settings
from django.db import models


class Course(models.Model):
    # Stored uppercase so codes are unique regardless of case.
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    faculty = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="teaching_courses",
        limit_choices_to={"role": "FACULTY"},
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="enrolled_courses",
        limit_choices_to={"role": "STUDENT"},
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.name}"
