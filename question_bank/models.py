from django.db import models

class Question(models.Model):
    class QuestionType(models.TextChoices):
        MCQ = "MCQ", "Multiple Choice"
        TRUE_FALSE = "TRUE_FALSE", "True/False"
        FILL_IN_THE_BLANK = "FILL_IN_THE_BLANK", "Fill in the Blank"
        SHORT_ANSWER = "SHORT_ANSWER", "Short Answer"

    class Difficulty(models.TextChoices):
        EASY = "EASY", "Easy"
        MEDIUM = "MEDIUM", "Medium"
        HARD = "HARD", "Hard"

    text = models.TextField()
    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices,
    )
    options = models.JSONField(default=list, blank=True)
    correct_answer = models.TextField()

    subject = models.CharField(max_length=100)
    topic = models.CharField(max_length=100)
    difficulty = models.CharField(
        max_length=10,
        choices=Difficulty.choices
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_question_type_display()}: {self.text[:60]}"
