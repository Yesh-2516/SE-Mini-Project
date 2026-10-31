from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone


class Attempt(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        SUBMITTED = "SUBMITTED", "Submitted"
        EXPIRED = "EXPIRED", "Expired"

    class SubmissionReason(models.TextChoices):
        MANUAL = "MANUAL", "Manual Submit"
        TIMEOUT = "TIMEOUT", "Timeout Auto-Submit"

    exam = models.ForeignKey(
        "exam_management.Exam",
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exam_attempts",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    started_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    submission_reason = models.CharField(
        max_length=20,
        choices=SubmissionReason.choices,
        null=True,
        blank=True,
    )
    allow_reattempt = models.BooleanField(default=False)
    objective_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    subjective_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    is_graded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]

    def is_expired(self, now=None):
        now = now or timezone.now()
        return now >= self.ends_at

    def remaining_seconds(self, now=None):
        if self.status != self.Status.IN_PROGRESS:
            return 0
        now = now or timezone.now()
        if now >= self.ends_at:
            return 0
        return max(0, int((self.ends_at - now).total_seconds()))

    def __str__(self):
        return f"{self.student.username} - {self.exam.title} ({self.status})"


class Response(models.Model):
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    question = models.ForeignKey(
        "question_bank.Question",
        on_delete=models.PROTECT,
        related_name="exam_responses",
    )
    submitted_answer = models.TextField(blank=True, default="")
    is_flagged = models.BooleanField(default=False)
    marks_obtained = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    feedback = models.TextField(blank=True, default="")
    evaluated_at = models.DateTimeField(null=True, blank=True)
    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="graded_responses",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_attempt_question",
            ),
        ]

    def __str__(self):
        return f"Attempt #{self.attempt_id} - Question #{self.question_id}"
