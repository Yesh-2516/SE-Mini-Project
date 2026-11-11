from django.contrib import admin
from django.urls import include, path

from config.health import health
from exam_delivery.views import AdminDiagnosticsView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("api/auth/", include("accounts.urls")),
    path("api/admin/users/", include("accounts.management_urls")),
    path("api/admin/courses/", include("courses.urls")),
    path("api/admin/diagnostics/", AdminDiagnosticsView.as_view(), name="admin-diagnostics"),
    path("api/", include("question_bank.urls")),
    path("api/exams/", include("exam_management.urls")),
    path("api/exams/", include("exam_delivery.urls")),
    path("api/", include("evaluation.urls")),
    path("api/", include("reports.urls")),
    path("", include("web.urls")),
]
