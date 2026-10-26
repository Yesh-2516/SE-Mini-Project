from django.urls import path

from courses.views import (
    CourseDetailView,
    CourseListCreateView,
    CourseMemberDetailView,
    CourseMembersView,
)

urlpatterns = [
    path("", CourseListCreateView.as_view(), name="course-list-create"),
    path("<int:pk>/", CourseDetailView.as_view(), name="course-detail"),
    path(
        "<int:pk>/faculty/",
        CourseMembersView.as_view(role="FACULTY", relation="faculty"),
        name="course-faculty",
    ),
    path(
        "<int:pk>/faculty/<int:user_id>/",
        CourseMemberDetailView.as_view(relation="faculty"),
        name="course-faculty-detail",
    ),
    path(
        "<int:pk>/students/",
        CourseMembersView.as_view(role="STUDENT", relation="students"),
        name="course-students",
    ),
    path(
        "<int:pk>/students/<int:user_id>/",
        CourseMemberDetailView.as_view(relation="students"),
        name="course-student-detail",
    ),
]
