from django.urls import path

from accounts.views import (
    CurrentUserView,
    LoginView,
    LogoutView,
    StudentRegistrationView,
)

urlpatterns = [
    path(
        "register/",
        StudentRegistrationView.as_view(),
        name="auth-register",
    ),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
]
