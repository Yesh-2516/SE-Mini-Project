from django.urls import path

from accounts.views import (
    ManagedAccountDetailView,
    ManagedAccountListCreateView,
    SetAccountActiveView,
)

urlpatterns = [
    path(
        "",
        ManagedAccountListCreateView.as_view(),
        name="admin-user-list-create",
    ),
    path(
        "<int:pk>/",
        ManagedAccountDetailView.as_view(),
        name="admin-user-detail",
    ),
    path(
        "<int:pk>/deactivate/",
        SetAccountActiveView.as_view(is_active=False),
        name="admin-user-deactivate",
    ),
    path(
        "<int:pk>/activate/",
        SetAccountActiveView.as_view(is_active=True),
        name="admin-user-activate",
    ),
]
