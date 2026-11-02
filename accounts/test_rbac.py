import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.test import APITestCase

from accounts.permissions import HasRole
from question_bank.models import Question

User = get_user_model()

# Routes anyone may call without logging in.
PUBLIC_ROUTES = {"auth-register", "auth-login"}

# Routes any logged-in user may call, whatever their role.
ANY_ROLE_ROUTES = {"auth-logout", "auth-me"}

# Routes accessible to authenticated students for exam sitting (OEP-F-030 - OEP-F-035).
STUDENT_EXAM_ROUTES = {
    "exam-attempt-start",
    "exam-attempt-detail",
    "exam-attempt-timer",
    "exam-attempt-autosave",
    "exam-attempt-submit",
    "exam-attempt-flag",
    "exam-attempt-navigator",
}


ENDPOINT_ROLES_DOC = settings.BASE_DIR / "docs" / "endpoint_roles.md"
DOC_ROW = re.compile(r"^\| `([\w-]+)` \| `(.+?)` \| (.+?) \| (.+?) \|$", re.MULTILINE)


def iter_api_routes(patterns=None, prefix=""):
    """Yield (route, url pattern) for every URL under /api/."""

    if patterns is None:
        patterns = get_resolver().url_patterns

    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from iter_api_routes(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern) and route.startswith("api/"):
            yield route, pattern


def view_class(pattern):
    callback = pattern.callback
    return getattr(callback, "view_class", None) or getattr(callback, "cls", None)


def concrete_path(route):
    """Turn 'api/exams/<int:pk>/' into '/api/exams/1/'."""

    parts = []
    for part in route.split("/"):
        parts.append("1" if part.startswith("<") else part)
    return "/" + "/".join(parts)


def implemented_methods(cls):
    return [
        method
        for method in ("get", "post", "put", "patch", "delete")
        if hasattr(cls, method)
    ]


class EndpointRegistryTests(APITestCase):
    """TC-Auth-03: role checks run on the server for every endpoint."""

    def setUp(self):
        self.student = User.objects.create_user(
            username="rbac_student",
            password="unused-Passw0rd!",
            role=User.Role.STUDENT,
        )

    def test_every_api_route_is_a_drf_view(self):
        for route, pattern in iter_api_routes():
            with self.subTest(route=route):
                self.assertIsNotNone(
                    view_class(pattern),
                    "Plain Django views skip DRF permission checks.",
                )

    def test_only_public_routes_allow_anonymous_access(self):
        for route, pattern in iter_api_routes():
            permissions = view_class(pattern).permission_classes
            with self.subTest(route=route):
                if pattern.name in PUBLIC_ROUTES:
                    self.assertIn(AllowAny, permissions)
                else:
                    self.assertTrue(permissions)
                    self.assertNotIn(AllowAny, permissions)

    def test_anonymous_requests_are_rejected_with_401(self):
        for route, pattern in iter_api_routes():
            if pattern.name in PUBLIC_ROUTES:
                continue
            path = concrete_path(route)
            for method in implemented_methods(view_class(pattern)):
                with self.subTest(route=route, method=method):
                    response = getattr(self.client, method)(path)
                    self.assertEqual(
                        response.status_code,
                        status.HTTP_401_UNAUTHORIZED,
                    )

    def test_students_are_forbidden_from_staff_endpoints(self):
        self.client.force_authenticate(user=self.student)

        for route, pattern in iter_api_routes():
            if pattern.name in PUBLIC_ROUTES | ANY_ROLE_ROUTES | STUDENT_EXAM_ROUTES:
                continue
            path = concrete_path(route)
            for method in implemented_methods(view_class(pattern)):
                with self.subTest(route=route, method=method):
                    response = getattr(self.client, method)(path)
                    self.assertEqual(
                        response.status_code,
                        status.HTTP_403_FORBIDDEN,
                    )


def required_role_permission(view):
    """Return the view's role permission, or None if it has no role check."""
    for permission in view.permission_classes:
        if issubclass(permission, HasRole):
            return permission
    return None


def documented_roles(view):
    """Describe a view's access the way docs/endpoint_roles.md does."""
    permissions = view.permission_classes
    if AllowAny in permissions:
        return "Anyone"
    role_permission = required_role_permission(view)
    if role_permission is None:
        return "Any logged-in user"
    return ", ".join(
        User.Role(role).label for role in role_permission.allowed_roles
    )


class EveryEndpointRoleCheckTests(APITestCase):
    """TC-Sec-06: the server checks the role on every endpoint."""

    def setUp(self):
        self.users = {
            role: User.objects.create_user(
                username=f"sec06_{role.lower()}",
                password="unused-Passw0rd!",
                role=role,
            )
            for role in User.Role.values
        }

    def test_every_protected_endpoint_has_a_role_check(self):
        for route, pattern in iter_api_routes():
            if pattern.name in PUBLIC_ROUTES | ANY_ROLE_ROUTES:
                continue
            with self.subTest(route=route):
                self.assertIsNotNone(required_role_permission(view_class(pattern)))

    def test_wrong_role_gets_403_on_every_protected_endpoint(self):
        for route, pattern in iter_api_routes():
            view = view_class(pattern)
            role_permission = required_role_permission(view)
            if role_permission is None:
                continue
            path = concrete_path(route)
            wrong_roles = set(User.Role.values) - set(role_permission.allowed_roles)
            for role in sorted(wrong_roles):
                self.client.force_authenticate(user=self.users[role])
                for method in implemented_methods(view):
                    with self.subTest(route=route, method=method, role=role):
                        response = getattr(self.client, method)(path)
                        self.assertEqual(
                            response.status_code,
                            status.HTTP_403_FORBIDDEN,
                        )

    def test_endpoint_role_list_matches_the_code(self):
        documented = {
            name: (path, methods, roles)
            for name, path, methods, roles in DOC_ROW.findall(
                ENDPOINT_ROLES_DOC.read_text(encoding="utf-8")
            )
        }
        actual = {}
        for route, pattern in iter_api_routes():
            view = view_class(pattern)
            actual[pattern.name] = (
                f"/{route}",
                ", ".join(m.upper() for m in implemented_methods(view)),
                documented_roles(view),
            )

        self.assertEqual(documented, actual)


class RoleMatrixTests(APITestCase):
    """TC-Auth-03: each role reaches only the endpoints it is allowed to use."""

    def setUp(self):
        self.users = {
            role: User.objects.create_user(
                username=f"rbac_{role.lower()}",
                password="unused-Passw0rd!",
                role=role,
            )
            for role in User.Role.values
        }
        self.question = Question.objects.create(
            text="2 + 2 = ?",
            question_type=Question.QuestionType.MCQ,
            options=["3", "4"],
            correct_answer="4",
            subject="Maths",
            topic="Arithmetic",
            difficulty=Question.Difficulty.EASY,
        )

    def get_as(self, role, path):
        self.client.force_authenticate(user=self.users[role])
        return self.client.get(path)

    def test_question_bank_access_by_role(self):
        path = f"/api/questions/{self.question.id}/"

        self.assertEqual(self.get_as("ADMIN", path).status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_as("FACULTY", path).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.get_as("STUDENT", path).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_exam_management_access_by_role(self):
        path = "/api/exams/"

        self.assertEqual(self.get_as("ADMIN", path).status_code, status.HTTP_200_OK)
        self.assertEqual(self.get_as("FACULTY", path).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.get_as("STUDENT", path).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_student_cannot_modify_or_import_questions(self):
        self.client.force_authenticate(user=self.users["STUDENT"])

        patch = self.client.patch(
            f"/api/questions/{self.question.id}/",
            {"text": "changed"},
            format="json",
        )
        delete = self.client.delete(f"/api/questions/{self.question.id}/")
        create = self.client.post("/api/questions/", {}, format="json")
        import_ = self.client.post("/api/questions/import/", {})

        for response in (patch, delete, create, import_):
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.question.refresh_from_db()
        self.assertEqual(self.question.text, "2 + 2 = ?")

    def test_every_role_can_read_its_own_profile(self):
        for role in User.Role.values:
            with self.subTest(role=role):
                response = self.get_as(role, "/api/auth/me/")
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["role"], role)

    def test_deactivated_user_loses_access(self):
        faculty = self.users["FACULTY"]
        faculty.is_active = False
        faculty.save()

        response = self.get_as("FACULTY", "/api/exams/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
