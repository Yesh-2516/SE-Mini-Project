from django.contrib import admin

from question_bank.models import Question


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "text", "question_type", "created_at")
    list_filter = ("question_type", "created_at")
    search_fields = ("text",)
    ordering = ("-created_at",)