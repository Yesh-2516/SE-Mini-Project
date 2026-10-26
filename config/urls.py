from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("question_bank.urls")),
    path("api/exams/", include("exam_management.urls")),
]
