from django.urls import path
from django.views.generic import RedirectView

from web import staff_views
from web.views import dashboard, login_page, logout_page, system_health, take_exam

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="web-dashboard"), name="web-home"),
    path("login/", login_page, name="web-login"),
    path("logout/", logout_page, name="web-logout"),
    path("dashboard/", dashboard, name="web-dashboard"),
    path("exams/<int:exam_id>/take/", take_exam, name="web-take-exam"),
    path("system-health/", system_health, name="web-system-health"),
    # Faculty and Admin
    path("grading/", staff_views.grading_queue, name="web-grading"),
    path(
        "grading/responses/<int:response_id>/",
        staff_views.grade_response,
        name="web-grade-response",
    ),
    path("reports/", staff_views.report_list, name="web-reports"),
    path("reports/exams/<int:exam_id>/", staff_views.report_detail, name="web-report"),
    # Student
    path("results/", staff_views.my_results, name="web-results"),
    path("results/<int:attempt_id>/", staff_views.scorecard, name="web-scorecard"),
    # Admin
    path("audit-log/", staff_views.audit_log, name="web-audit-log"),
]
