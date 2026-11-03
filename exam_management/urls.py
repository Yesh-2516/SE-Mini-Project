
from django.urls import path

from exam_management.views import (
    ExamCourseDetailView,
    ExamCoursesView,
    ExamDetailView,
    ExamListCreateView,
    ExamPublishView,
    ExamQuestionMarksView,
    ExamUnpublishView,
    ManualAssemblyView,
    RuleGenerationView,
)

urlpatterns = [
    path("", ExamListCreateView.as_view(), name="exam-list-create"),
    path("<int:pk>/", ExamDetailView.as_view(), name="exam-detail"),
    path(
        "<int:pk>/assemble/",
        ManualAssemblyView.as_view(),
        name="exam-manual-assembly",
    ),
    path(
        "<int:pk>/generate/",
        RuleGenerationView.as_view(),
        name="exam-rule-generation",
    ),
    path(
        "<int:pk>/questions/<int:question_id>/marks/",
        ExamQuestionMarksView.as_view(),
        name="exam-question-marks",
    ),
    path(
        "<int:pk>/courses/",
        ExamCoursesView.as_view(),
        name="exam-courses",
    ),
    path(
        "<int:pk>/courses/<int:course_id>/",
        ExamCourseDetailView.as_view(),
        name="exam-course-detail",
    ),
    path(
        "<int:pk>/publish/",
        ExamPublishView.as_view(),
        name="exam-publish",
    ),
    path(
        "<int:pk>/unpublish/",
        ExamUnpublishView.as_view(),
        name="exam-unpublish",
    ),
]
