
from django.urls import path

from exam_management.views import (
    ExamDetailView,
    ExamListCreateView,
    ExamQuestionMarksView,
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
]
