from django.urls import path

from evaluation.views import (
    EvaluateResponseView,
    GradingQueueView,
    ScorecardDetailView,
    ScorecardListView,
)

urlpatterns = [
    path(
        "evaluation/pending/",
        GradingQueueView.as_view(),
        name="evaluation-pending",
    ),
    path(
        "evaluation/responses/<int:response_id>/",
        EvaluateResponseView.as_view(),
        name="evaluation-response-grade",
    ),
    path(
        "results/",
        ScorecardListView.as_view(),
        name="result-list",
    ),
    path(
        "results/<int:attempt_id>/",
        ScorecardDetailView.as_view(),
        name="result-scorecard",
    ),
]
