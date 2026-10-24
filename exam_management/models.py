
from django.db import models


class Exam(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"

    title = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    duration_minutes = models.PositiveIntegerField(default=60)
    negative_marking_enabled = models.BooleanField(default=False)
    negative_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    questions = models.ManyToManyField(
        "question_bank.Question",
        through="ExamQuestion",
        related_name="exams",
    )

    @property
    def total_marks(self):
        return sum(
            item.marks for item in self.exam_questions.all()
        )

    def __str__(self):
        return self.title


class ExamQuestion(models.Model):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="exam_questions",
    )
    question = models.ForeignKey(
        "question_bank.Question",
        on_delete=models.PROTECT,
        related_name="exam_question_links",
    )
    position = models.PositiveIntegerField()
    marks = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "question"],
                name="unique_question_per_exam",
            ),
            models.UniqueConstraint(
                fields=["exam", "position"],
                name="unique_exam_question_position",
            ),
        ]

    def __str__(self):
        return f"{self.exam.title} - Question {self.position}"
