from django.urls import path

from reports.views import ExamReportExportView, ExamReportView, QuestionBreakdownView

urlpatterns = [
    path(
        "reports/exams/<int:exam_id>/",
        ExamReportView.as_view(),
        name="report-exam",
    ),
    path(
        "reports/exams/<int:exam_id>/export/",
        ExamReportExportView.as_view(),
        name="report-exam-export",
    ),
    path(
        "reports/exams/<int:exam_id>/questions/",
        QuestionBreakdownView.as_view(),
        name="report-exam-questions",
    ),
]
