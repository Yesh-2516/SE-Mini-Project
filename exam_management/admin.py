from django.contrib import admin, messages
from django.db.models import Max
from rest_framework.exceptions import APIException

from courses.models import Course
from exam_management.models import Exam, ExamQuestion
from exam_management.services import publish_exam, unpublish_exam


def _error_text(exc):
    """Flatten a DRF error detail (str, list or dict) into one readable line."""

    detail = getattr(exc, "detail", exc)
    if isinstance(detail, dict):
        return " ".join(_error_text(value) for value in detail.values())
    if isinstance(detail, (list, tuple)):
        return " ".join(_error_text(value) for value in detail)
    return str(detail)


def _is_faculty(user):
    return getattr(user, "role", None) == "FACULTY" and not user.is_superuser


class ExamQuestionInline(admin.TabularInline):
    model = ExamQuestion
    fields = ("question", "marks")
    autocomplete_fields = ("question",)
    extra = 3
    verbose_name = "question"
    verbose_name_plural = "Questions (in the order students see them)"

    def _locked(self, obj):
        return obj is not None and obj.status != Exam.Status.DRAFT

    def has_add_permission(self, request, obj=None):
        return not self._locked(obj) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return not self._locked(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self._locked(obj) and super().has_delete_permission(request, obj)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    """Build, assign and publish exams without using the API."""

    list_display = (
        "title",
        "status",
        "course_list",
        "question_count",
        "total_marks",
        "availability_start",
        "availability_end",
    )
    list_filter = ("status", "courses")
    search_fields = ("title",)
    filter_horizontal = ("courses",)
    inlines = [ExamQuestionInline]
    actions = ["publish_selected", "unpublish_selected"]
    fieldsets = (
        (None, {"fields": ("title", "status", "duration_minutes")}),
        (
            "When students can start it",
            {
                "description": (
                    "Times are in server time (UTC). India time is UTC + 5:30, "
                    "so 2:00 PM IST is 08:30 here."
                ),
                "fields": ("availability_start", "availability_end"),
            },
        ),
        (
            "Who takes it",
            {
                "description": (
                    "Students enrolled in these courses see the exam once it is "
                    "published."
                ),
                "fields": ("courses",),
            },
        ),
        (
            "Scoring",
            {"fields": ("negative_marking_enabled", "negative_marks")},
        ),
    )

    @admin.display(description="Courses")
    def course_list(self, obj):
        return ", ".join(obj.courses.values_list("code", flat=True)) or "-"

    @admin.display(description="Questions")
    def question_count(self, obj):
        return obj.exam_questions.count()

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.status != Exam.Status.DRAFT:
            # Published exams are frozen; unpublish first to change them.
            return [
                field
                for fieldset in self.fieldsets
                for field in fieldset[1]["fields"]
            ]
        return ["status"]

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Faculty may only assign courses they teach, matching the API rule.
        if db_field.name == "courses" and _is_faculty(request.user):
            kwargs["queryset"] = Course.objects.filter(faculty=request.user)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_formset(self, request, form, formset, change):
        if formset.model is not ExamQuestion:
            return super().save_formset(request, form, formset, change)

        instances = formset.save(commit=False)
        for removed in formset.deleted_objects:
            removed.delete()

        exam = form.instance
        next_position = (
            exam.exam_questions.aggregate(top=Max("position"))["top"] or 0
        ) + 1
        for item in instances:
            if item.position is None:
                item.position = next_position
                next_position += 1
            item.save()
        formset.save_m2m()

    @admin.action(description="Publish selected exams (students can see them)")
    def publish_selected(self, request, queryset):
        for exam in queryset:
            try:
                publish_exam(exam=exam)
            except APIException as exc:
                self.message_user(
                    request,
                    f"Couldn't publish “{exam}”: {_error_text(exc)}",
                    messages.ERROR,
                )
            else:
                self.message_user(
                    request, f"Published “{exam}”.", messages.SUCCESS
                )

    @admin.action(description="Unpublish selected exams (back to draft)")
    def unpublish_selected(self, request, queryset):
        for exam in queryset:
            try:
                unpublish_exam(exam=exam)
            except APIException as exc:
                self.message_user(
                    request,
                    f"Couldn't unpublish “{exam}”: {_error_text(exc)}",
                    messages.ERROR,
                )
            else:
                self.message_user(
                    request, f"“{exam}” is a draft again.", messages.SUCCESS
                )
