from django.urls import path

from question_bank.views import QuestionListCreateView

urlpatterns = [
    path("questions/", QuestionListCreateView.as_view(), name="question-list-create"),
]