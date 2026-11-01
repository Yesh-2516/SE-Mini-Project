from django.contrib import admin
from exam_delivery.models import Attempt, Response


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "student",
        "exam",
        "status",
        "started_at",
        "ends_at",
        "submitted_at",
        "allow_reattempt",
        "total_score",
        "is_graded",
    )
    list_filter = ("status", "is_graded", "allow_reattempt")
    search_fields = ("student__username", "exam__title")


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "attempt",
        "question",
        "is_flagged",
        "marks_obtained",
        "evaluated_at",
    )
    list_filter = ("is_flagged",)
    search_fields = ("attempt__student__username", "question__text")
