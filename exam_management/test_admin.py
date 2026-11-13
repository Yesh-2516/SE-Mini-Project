from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from courses.models import Course
from exam_management.models import Exam
from exam_management.services import get_exams_visible_to_student
from question_bank.models import Question


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="boss", email="boss@example.com", password="pass12345"
    )


@pytest.fixture
def setup(db):
    student = User.objects.create_user(
        username="stu", password="pass12345", role=User.Role.STUDENT
    )
    course = Course.objects.create(code="CS101", name="Intro")
    course.students.add(student)
    q1 = Question.objects.create(
        text="2+2?", question_type="MCQ", options=["3", "4"], correct_answer="4"
    )
    q2 = Question.objects.create(
        text="Sky is blue", question_type="TRUE_FALSE", correct_answer="True"
    )
    return student, course, q1, q2


def _fmt(dt):
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")


def _add_form(course, questions, start, end):
    start_date, start_time = _fmt(start)
    end_date, end_time = _fmt(end)
    data = {
        "title": "Midterm",
        "duration_minutes": "30",
        "availability_start_0": start_date,
        "availability_start_1": start_time,
        "availability_end_0": end_date,
        "availability_end_1": end_time,
        "courses": [str(course.pk)],
        "negative_marks": "0",
        "exam_questions-TOTAL_FORMS": str(len(questions)),
        "exam_questions-INITIAL_FORMS": "0",
        "exam_questions-MIN_NUM_FORMS": "0",
        "exam_questions-MAX_NUM_FORMS": "1000",
    }
    for i, (question, marks) in enumerate(questions):
        data[f"exam_questions-{i}-question"] = str(question.pk)
        data[f"exam_questions-{i}-marks"] = str(marks)
    return data


def test_admin_builds_assigns_and_publishes_exam(client, admin_user, setup):
    student, course, q1, q2 = setup
    client.force_login(admin_user)
    now = timezone.now()

    response = client.post(
        reverse("admin:exam_management_exam_add"),
        _add_form(course, [(q1, 2), (q2, 1)], now - timedelta(hours=1), now + timedelta(days=1)),
    )
    assert response.status_code == 302, response.content.decode()[:2000]

    exam = Exam.objects.get(title="Midterm")
    assert exam.status == Exam.Status.DRAFT
    assert list(exam.exam_questions.values_list("question_id", "position", "marks")) == [
        (q1.pk, 1, 2),
        (q2.pk, 2, 1),
    ]
    assert list(exam.courses.all()) == [course]

    client.post(
        reverse("admin:exam_management_exam_changelist"),
        {"action": "publish_selected", "_selected_action": [exam.pk]},
    )
    exam.refresh_from_db()
    assert exam.status == Exam.Status.PUBLISHED
    assert exam in get_exams_visible_to_student(student)


def test_publish_action_reports_missing_requirements(client, admin_user, setup):
    exam = Exam.objects.create(title="Empty")
    client.force_login(admin_user)

    response = client.post(
        reverse("admin:exam_management_exam_changelist"),
        {"action": "publish_selected", "_selected_action": [exam.pk]},
        follow=True,
    )

    exam.refresh_from_db()
    assert exam.status == Exam.Status.DRAFT
    page = response.content.decode()
    assert "Add at least one question before publishing." in page
    assert "Assign at least one course before publishing." in page


def test_faculty_only_sees_courses_they_teach(client, setup):
    _, course, _, _ = setup
    other = Course.objects.create(code="MA201", name="Maths")
    teacher = User.objects.create_user(
        username="prof", password="pass12345", role=User.Role.FACULTY, is_staff=True
    )
    course.faculty.add(teacher)
    from django.contrib.auth.models import Permission

    teacher.user_permissions.add(
        *Permission.objects.filter(content_type__app_label="exam_management")
    )
    client.force_login(teacher)

    page = client.get(reverse("admin:exam_management_exam_add")).content.decode()

    assert "CS101" in page
    assert "MA201" not in page
