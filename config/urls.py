from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/admin/users/", include("accounts.management_urls")),
    path("api/admin/courses/", include("courses.urls")),
    path("api/", include("question_bank.urls")),
    path("api/exams/", include("exam_management.urls")),
]
