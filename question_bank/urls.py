
from django.urls import path

from question_bank.views import (
    QuestionListCreateView,
    QuestionDetailView,
    download_question_template,
    import_questions,
)

urlpatterns = [
    path(
        "questions/import/template/",
        download_question_template,
        name="question-import-template",
    ),
    path(
        "questions/",
        QuestionListCreateView.as_view(),
        name="question-list-create",
    ),
    path(
        "questions/import/",
        import_questions,
        name="question-import",
    ),
    path(
        "questions/<int:pk>/",
        QuestionDetailView.as_view(),
        name="question-detail",
    ),
]
