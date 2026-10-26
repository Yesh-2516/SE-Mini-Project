from django.urls import path

from accounts.views import StudentRegistrationView

urlpatterns = [
    path(
        "register/",
        StudentRegistrationView.as_view(),
        name="auth-register",
    ),
]
