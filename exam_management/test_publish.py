from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course
from exam_delivery.models import Attempt
from exam_management.models import Exam, ExamQuestion
from exam_management.services import (
    ensure_student_can_sit,
    get_exams_visible_to_student,
    ExamNotAvailable,
)
from question_bank.models import Question

User = get_user_model()


class PublishBaseTestCase(APITestCase):
    def setUp(self):
        self.now = timezone.now()
        self.admin = User.objects.create_user(
            username="pub_admin", password="StrongPassword123!", role=User.Role.ADMIN
        )
        self.faculty = User.objects.create_user(
            username="pub_faculty", password="StrongPassword123!", role=User.Role.FACULTY
        )
        self.other_faculty = User.objects.create_user(
            username="pub_faculty2", password="StrongPassword123!", role=User.Role.FACULTY
        )
        self.student = User.objects.create_user(
            username="pub_student", password="StrongPassword123!", role=User.Role.STUDENT
        )
        self.outsider = User.objects.create_user(
            username="pub_outsider", password="StrongPassword123!", role=User.Role.STUDENT
        )

        self.course = Course.objects.create(code="CS101", name="Intro")
        self.course.faculty.add(self.faculty)
        self.course.students.add(self.student)
        self.other_course = Course.objects.create(code="CS202", name="Advanced")
        self.other_course.faculty.add(self.other_faculty)

        self.question = Question.objects.create(
            text="2 + 2 = ?",
            question_type=Question.QuestionType.MCQ,
            options=["3", "4"],
            correct_answer="4",
            subject="Maths",
            topic="Arithmetic",
            difficulty=Question.Difficulty.EASY,
        )
        self.exam = Exam.objects.create(
            title="Publishable",
            duration_minutes=30,
            availability_start=self.now - timedelta(minutes=5),
            availability_end=self.now + timedelta(hours=2),
        )
        ExamQuestion.objects.create(exam=self.exam, question=self.question, position=1)

    def url(self, suffix=""):
        return f"/api/exams/{self.exam.id}/{suffix}"

    def ready_exam(self):
        self.exam.courses.add(self.course)
        return self.exam


class AssignCourseTests(PublishBaseTestCase):
    def test_admin_can_assign_any_course(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url("courses/"),
            {"course_ids": [self.course.id, self.other_course.id]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(self.exam.courses.values_list("id", flat=True)),
            {self.course.id, self.other_course.id},
        )

    def test_assigning_twice_is_harmless(self):
        self.client.force_authenticate(user=self.admin)
        for _ in range(2):
            response = self.client.post(
                self.url("courses/"), {"course_ids": [self.course.id]}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.exam.courses.count(), 1)

    def test_faculty_can_assign_their_own_course(self):
        self.client.force_authenticate(user=self.faculty)
        response = self.client.post(
            self.url("courses/"), {"course_ids": [self.course.id]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_faculty_cannot_assign_a_course_they_do_not_teach(self):
        self.client.force_authenticate(user=self.faculty)
        response = self.client.post(
            self.url("courses/"),
            {"course_ids": [self.course.id, self.other_course.id]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.exam.courses.count(), 0)

    def test_unknown_course_is_rejected(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url("courses/"), {"course_ids": [99999]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_course_list_is_rejected(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.url("courses/"), {"course_ids": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_course_can_be_removed_from_a_draft_exam(self):
        self.ready_exam()
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(self.url(f"courses/{self.course.id}/"))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.exam.courses.count(), 0)

    def test_removing_a_course_that_is_not_assigned_is_rejected(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(self.url(f"courses/{self.course.id}/"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_courses_cannot_change_while_published(self):
        self.ready_exam()
        self.client.force_authenticate(user=self.admin)
        self.client.post(self.url("publish/"))

        add = self.client.post(
            self.url("courses/"), {"course_ids": [self.other_course.id]}, format="json"
        )
        remove = self.client.delete(self.url(f"courses/{self.course.id}/"))

        self.assertEqual(add.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(remove.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.exam.courses.count(), 1)

    def test_students_cannot_assign_courses(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            self.url("courses/"), {"course_ids": [self.course.id]}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_exam_detail_lists_assigned_course_ids(self):
        self.ready_exam()
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url())
        self.assertEqual(response.data["courses"], [self.course.id])


class PublishRuleTests(PublishBaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.faculty)

    def test_publish_succeeds_when_exam_is_ready(self):
        self.ready_exam()
        response = self.client.post(self.url("publish/"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.Status.PUBLISHED)

    def test_publish_needs_a_course(self):
        response = self.client.post(self.url("publish/"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("courses", response.data)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.Status.DRAFT)

    def test_publish_needs_questions(self):
        self.ready_exam()
        ExamQuestion.objects.filter(exam=self.exam).delete()
        response = self.client.post(self.url("publish/"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("questions", response.data)

    def test_publish_needs_an_availability_window(self):
        self.ready_exam()
        Exam.objects.filter(pk=self.exam.pk).update(
            availability_start=None, availability_end=None
        )
        response = self.client.post(self.url("publish/"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("availability", response.data)

    def test_publish_rejects_a_window_that_has_already_closed(self):
        self.ready_exam()
        Exam.objects.filter(pk=self.exam.pk).update(
            availability_start=self.now - timedelta(hours=3),
            availability_end=self.now - timedelta(hours=1),
        )
        response = self.client.post(self.url("publish/"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("availability_end", response.data)

    def test_publish_reports_every_problem_at_once(self):
        ExamQuestion.objects.filter(exam=self.exam).delete()
        response = self.client.post(self.url("publish/"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("questions", response.data)
        self.assertIn("courses", response.data)

    def test_publishing_twice_is_rejected(self):
        self.ready_exam()
        self.client.post(self.url("publish/"))
        response = self.client.post(self.url("publish/"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_unknown_exam_returns_404(self):
        response = self.client.post("/api/exams/99999/publish/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_published_exam_is_locked_for_editing(self):
        self.ready_exam()
        self.client.post(self.url("publish/"))
        response = self.client.patch(self.url(), {"title": "Changed"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        assemble = self.client.post(
            self.url("assemble/"), {"question_ids": [self.question.id]}, format="json"
        )
        self.assertEqual(assemble.status_code, status.HTTP_400_BAD_REQUEST)

    def test_students_cannot_publish_or_unpublish(self):
        self.ready_exam()
        self.client.force_authenticate(user=self.student)
        for action in ("publish/", "unpublish/"):
            response = self.client.post(self.url(action))
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.Status.DRAFT)


class UnpublishTests(PublishBaseTestCase):
    def setUp(self):
        super().setUp()
        self.ready_exam()
        self.client.force_authenticate(user=self.admin)
        self.client.post(self.url("publish/"))

    def test_unpublish_returns_exam_to_draft(self):
        response = self.client.post(self.url("unpublish/"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.Status.DRAFT)

    def test_unpublish_then_edit_then_republish(self):
        self.client.post(self.url("unpublish/"))
        edit = self.client.patch(self.url(), {"title": "Renamed"}, format="json")
        self.assertEqual(edit.status_code, status.HTTP_200_OK)
        republish = self.client.post(self.url("publish/"))
        self.assertEqual(republish.status_code, status.HTTP_200_OK)

    def test_unpublish_a_draft_is_rejected(self):
        self.client.post(self.url("unpublish/"))
        response = self.client.post(self.url("unpublish/"))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unpublish_is_blocked_once_a_student_has_started(self):
        self.client.force_authenticate(user=self.student)
        start = self.client.post(self.url("start/"))
        self.assertEqual(start.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.url("unpublish/"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.Status.PUBLISHED)


class StudentAccessTests(PublishBaseTestCase):
    def start_as(self, user):
        self.client.force_authenticate(user=user)
        return self.client.post(self.url("start/"))

    def test_enrolled_student_can_start_a_published_exam(self):
        self.ready_exam()
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.Status.PUBLISHED)
        self.assertEqual(self.start_as(self.student).status_code, status.HTTP_201_CREATED)

    def test_student_cannot_start_an_unpublished_exam(self):
        self.ready_exam()
        response = self.start_as(self.student)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "This exam is not available to you.")
        self.assertFalse(Attempt.objects.exists())

    def test_student_outside_the_course_cannot_start(self):
        self.ready_exam()
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.Status.PUBLISHED)
        response = self.start_as(self.outsider)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Attempt.objects.exists())

    def test_student_cannot_start_after_being_removed_from_the_course(self):
        self.ready_exam()
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.Status.PUBLISHED)
        self.course.students.remove(self.student)
        self.assertEqual(self.start_as(self.student).status_code, status.HTTP_403_FORBIDDEN)

    def test_unpublished_exam_in_a_closed_window_still_reports_not_open(self):
        Exam.objects.filter(pk=self.exam.pk).update(
            availability_start=self.now - timedelta(hours=3),
            availability_end=self.now - timedelta(hours=1),
        )
        response = self.start_as(self.student)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "This exam is not open.")

    def test_in_progress_attempt_can_still_be_resumed_after_removal_from_course(self):
        self.ready_exam()
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.Status.PUBLISHED)
        self.assertEqual(self.start_as(self.student).status_code, status.HTTP_201_CREATED)
        self.course.students.remove(self.student)
        self.assertEqual(self.start_as(self.student).status_code, status.HTTP_200_OK)

    def test_visible_exams_are_published_and_in_the_students_courses(self):
        self.ready_exam()
        draft = Exam.objects.create(title="Draft in course")
        draft.courses.add(self.course)
        elsewhere = Exam.objects.create(title="Other course", status=Exam.Status.PUBLISHED)
        elsewhere.courses.add(self.other_course)
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.Status.PUBLISHED)

        self.assertEqual(
            list(get_exams_visible_to_student(self.student)), [self.exam]
        )
        self.assertEqual(list(get_exams_visible_to_student(self.outsider)), [])

    def test_exam_assigned_to_two_shared_courses_is_listed_once(self):
        self.ready_exam()
        self.exam.courses.add(self.other_course)
        self.other_course.students.add(self.student)
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.Status.PUBLISHED)
        self.assertEqual(get_exams_visible_to_student(self.student).count(), 1)

    def test_ensure_student_can_sit_raises_for_unpublished_exam(self):
        self.ready_exam()
        with self.assertRaises(ExamNotAvailable):
            ensure_student_can_sit(exam=self.exam, student=self.student)
