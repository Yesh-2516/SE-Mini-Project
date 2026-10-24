
from django.urls import path

from exam_management.views import (
    ExamDetailView,
    ExamListCreateView,
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
]
