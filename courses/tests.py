from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course

User = get_user_model()

LIST_URL = "/api/admin/courses/"


def detail_url(course_id):
    return f"{LIST_URL}{course_id}/"


class CourseTestCase(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="portal_admin",
            password="unused-Passw0rd!",
            role=User.Role.ADMIN,
        )
        self.faculty = User.objects.create_user(
            username="prof.iyer",
            password="unused-Passw0rd!",
            role=User.Role.FACULTY,
        )
        self.other_faculty = User.objects.create_user(
            username="prof.rao",
            password="unused-Passw0rd!",
            role=User.Role.FACULTY,
        )
        self.student = User.objects.create_user(
            username="cs500",
            roll_number="CS500",
            password="unused-Passw0rd!",
            role=User.Role.STUDENT,
        )
        self.other_student = User.objects.create_user(
            username="cs501",
            roll_number="CS501",
            password="unused-Passw0rd!",
            role=User.Role.STUDENT,
        )
        self.course = Course.objects.create(
            code="CS301",
            name="Software Engineering",
        )
        self.client.force_authenticate(user=self.admin)


class CourseCrudTests(CourseTestCase):
    """TC-Admin-02: admin creates, edits and deletes courses."""

    def test_admin_creates_course(self):
        response = self.client.post(
            LIST_URL,
            {"code": " cs302 ", "name": "Databases", "description": "RDBMS"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "CS302")
        self.assertEqual(response.data["faculty"], [])
        self.assertEqual(response.data["students"], [])

    def test_duplicate_course_code_is_rejected(self):
        response = self.client.post(
            LIST_URL,
            {"code": "cs301", "name": "Another"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_blank_course_fields_are_rejected(self):
        response = self.client.post(
            LIST_URL,
            {"code": "   ", "name": "   "},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)
        self.assertIn("name", response.data)

    def test_admin_lists_courses(self):
        Course.objects.create(code="CS100", name="Intro")

        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [course["code"] for course in response.data],
            ["CS100", "CS301"],
        )

    def test_admin_edits_course(self):
        response = self.client.patch(
            detail_url(self.course.id),
            {"name": "Software Engineering II", "code": "cs301"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.course.refresh_from_db()
        self.assertEqual(self.course.name, "Software Engineering II")

    def test_edit_rejects_code_of_another_course(self):
        Course.objects.create(code="CS100", name="Intro")

        response = self.client.patch(
            detail_url(self.course.id),
            {"code": "cs100"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_deletes_course_and_its_mappings(self):
        self.course.faculty.add(self.faculty)
        self.course.students.add(self.student)

        response = self.client.delete(detail_url(self.course.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Course.objects.exists())
        self.assertTrue(User.objects.filter(pk=self.faculty.pk).exists())
        self.assertFalse(self.student.enrolled_courses.exists())


class CourseMappingTests(CourseTestCase):
    """TC-Admin-02: admin maps Faculty and Students to a course."""

    def test_admin_maps_faculty_to_course(self):
        response = self.client.post(
            f"{detail_url(self.course.id)}faculty/",
            {"user_ids": [self.faculty.id, self.other_faculty.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {user["id"] for user in response.data["faculty"]},
            {self.faculty.id, self.other_faculty.id},
        )
        self.assertIn(self.course, self.faculty.teaching_courses.all())

    def test_admin_maps_students_to_course(self):
        response = self.client.post(
            f"{detail_url(self.course.id)}students/",
            {"user_ids": [self.student.id, self.other_student.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {user["id"] for user in response.data["students"]},
            {self.student.id, self.other_student.id},
        )
        self.assertIn(self.course, self.student.enrolled_courses.all())

    def test_mapping_is_idempotent(self):
        url = f"{detail_url(self.course.id)}students/"

        self.client.post(url, {"user_ids": [self.student.id]}, format="json")
        response = self.client.post(url, {"user_ids": [self.student.id]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.course.students.count(), 1)

    def test_student_cannot_be_mapped_as_faculty(self):
        response = self.client.post(
            f"{detail_url(self.course.id)}faculty/",
            {"user_ids": [self.faculty.id, self.student.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.course.faculty.exists())

    def test_faculty_cannot_be_mapped_as_student(self):
        response = self.client.post(
            f"{detail_url(self.course.id)}students/",
            {"user_ids": [self.faculty.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_user_ids_are_rejected(self):
        response = self.client.post(
            f"{detail_url(self.course.id)}students/",
            {"user_ids": [self.student.id, 99999]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.course.students.exists())

    def test_deactivated_accounts_cannot_be_mapped(self):
        self.student.is_active = False
        self.student.save()

        response = self.client.post(
            f"{detail_url(self.course.id)}students/",
            {"user_ids": [self.student.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_or_duplicate_user_ids_are_rejected(self):
        url = f"{detail_url(self.course.id)}students/"

        empty = self.client.post(url, {"user_ids": []}, format="json")
        duplicate = self.client.post(
            url,
            {"user_ids": [self.student.id, self.student.id]},
            format="json",
        )

        self.assertEqual(empty.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    def test_mapping_unknown_course_returns_404(self):
        response = self.client.post(
            f"{detail_url(99999)}students/",
            {"user_ids": [self.student.id]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_unmaps_faculty_and_student(self):
        self.course.faculty.add(self.faculty)
        self.course.students.add(self.student, self.other_student)

        faculty = self.client.delete(
            f"{detail_url(self.course.id)}faculty/{self.faculty.id}/"
        )
        student = self.client.delete(
            f"{detail_url(self.course.id)}students/{self.student.id}/"
        )

        self.assertEqual(faculty.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(student.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(self.course.faculty.exists())
        self.assertEqual(list(self.course.students.all()), [self.other_student])

    def test_unmapping_user_not_in_course_returns_404(self):
        response = self.client.delete(
            f"{detail_url(self.course.id)}students/{self.student.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_course_detail_shows_mappings(self):
        self.course.faculty.add(self.faculty)
        self.course.students.add(self.student)

        response = self.client.get(detail_url(self.course.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["faculty"][0]["id"], self.faculty.id)
        self.assertEqual(response.data["students"][0]["roll_number"], "CS500")


class CourseAccessTests(CourseTestCase):
    def test_faculty_and_students_cannot_manage_courses(self):
        for user in (self.faculty, self.student):
            self.client.force_authenticate(user=user)
            with self.subTest(role=user.role):
                listing = self.client.get(LIST_URL)
                create = self.client.post(
                    LIST_URL,
                    {"code": "X1", "name": "X"},
                    format="json",
                )
                enrol = self.client.post(
                    f"{detail_url(self.course.id)}students/",
                    {"user_ids": [self.student.id]},
                    format="json",
                )

                for response in (listing, create, enrol):
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.assertFalse(self.course.students.exists())
