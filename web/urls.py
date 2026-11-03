from django.urls import path
from django.views.generic import RedirectView

from web.views import dashboard, login_page, logout_page, take_exam

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="web-dashboard"), name="web-home"),
    path("login/", login_page, name="web-login"),
    path("logout/", logout_page, name="web-logout"),
    path("dashboard/", dashboard, name="web-dashboard"),
    path("exams/<int:exam_id>/take/", take_exam, name="web-take-exam"),
]
