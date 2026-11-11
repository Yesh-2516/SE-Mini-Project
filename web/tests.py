import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.audit_models import AuditLog
from courses.models import Course
from exam_delivery.models import Attempt
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

User = get_user_model()

PASSWORD = "Str0ng-Passphrase!"
WRONG_PASSWORD = "Wrong-Passphrase!"
ANSWER_KEY = "The secret correct answer"


class WebTestCase(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.student = User.objects.create_user(
            username="meera",
            password=PASSWORD,
            role=User.Role.STUDENT,
        )
        self.faculty = User.objects.create_user(
            username="prof.iyer",
            password=PASSWORD,
            role=User.Role.FACULTY,
        )
        self.exam = self.create_exam("Open exam")

    def create_exam(self, title, starts=-10, ends=120, with_question=True):
        exam = Exam.objects.create(
            title=title,
            duration_minutes=30,
            availability_start=self.now + timedelta(minutes=starts),
            availability_end=self.now + timedelta(minutes=ends),
        )

        # OEP-F-024: each helper-created web test exam is published and assigned to its student's course.
        course = Course.objects.create(
            code=f"WEB{exam.pk:04d}",
            name=f"{title} Course",
        )
        course.students.add(self.student)
        exam.courses.add(course)
        exam.status = Exam.Status.PUBLISHED
        exam.save(update_fields=["status"])

        if with_question:
            question = Question.objects.create(
                text="Pick one",
                question_type=Question.QuestionType.MCQ,
                options=[ANSWER_KEY, "Wrong option"],
                correct_answer=ANSWER_KEY,
                subject="General",
                topic="General",
                difficulty=Question.Difficulty.EASY,
            )
            ExamQuestion.objects.create(exam=exam, question=question, position=1)
        return exam

    def create_attempt(self, exam=None, **fields):
        fields.setdefault("started_at", self.now - timedelta(minutes=5))
        fields.setdefault("ends_at", self.now + timedelta(minutes=20))
        return Attempt.objects.create(
            exam=exam or self.exam,
            student=self.student,
            **fields,
        )

    def log_in(self, password=PASSWORD, username="meera", **extra):
        return self.client.post(
            reverse("web-login"),
            {"identifier": username, "password": password, **extra},
        )


class StaticFilesTests(TestCase):
    def test_collectstatic_gathers_the_site_files(self):
        with tempfile.TemporaryDirectory() as static_root:
            with self.settings(STATIC_ROOT=static_root):
                call_command("collectstatic", interactive=False, verbosity=0)

            self.assertTrue(Path(static_root, "web", "exam.js").exists())
            self.assertTrue(Path(static_root, "web", "site.css").exists())


class LoginPageTests(WebTestCase):
    def test_login_page_labels_every_field(self):
        response = self.client.get(reverse("web-login"))

        self.assertContains(response, '<label class="form-label" for="id_identifier">')
        self.assertContains(response, '<label class="form-label" for="id_password">')

    def test_login_redirects_to_dashboard_and_is_audited(self):
        response = self.log_in()

        self.assertRedirects(response, reverse("web-dashboard"))
        self.assertTrue(
            AuditLog.objects.filter(event_type="login.success", actor=self.student).exists()
        )

    @override_settings(TLS_ENABLED=True)
    def test_login_behind_the_proxy_audits_the_client_address(self):
        self.client.post(
            reverse("web-login"),
            {"identifier": "meera", "password": PASSWORD},
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_FORWARDED_FOR="203.0.113.9",
        )

        entry = AuditLog.objects.get(event_type="login.success")
        self.assertEqual(entry.ip_address, "203.0.113.9")

    def test_wrong_password_shows_an_error(self):
        response = self.log_in(WRONG_PASSWORD)

        self.assertEqual(response.status_code, 401)
        self.assertContains(response, "match an account", status_code=401)

    def test_fifth_failure_locks_the_account(self):
        for _ in range(5):
            response = self.log_in(WRONG_PASSWORD)

        self.assertContains(response, "temporarily locked", status_code=423)

    def test_correct_password_is_refused_while_locked(self):
        for _ in range(5):
            self.log_in(WRONG_PASSWORD)

        response = self.log_in()

        self.assertEqual(response.status_code, 423)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_returns_to_a_local_next_page(self):
        target = reverse("web-take-exam", args=[self.exam.id])

        response = self.log_in(next=target)

        self.assertRedirects(response, target)

    def test_login_ignores_an_external_next_page(self):
        response = self.log_in(next="https://evil.example/")

        self.assertRedirects(response, reverse("web-dashboard"))

    def test_logged_in_user_skips_the_login_page(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("web-login"))

        self.assertRedirects(response, reverse("web-dashboard"))

    def test_logout_needs_post_and_ends_the_session(self):
        self.client.force_login(self.student)

        self.assertEqual(self.client.get(reverse("web-logout")).status_code, 405)
        self.client.post(reverse("web-logout"))

        self.assertNotIn("_auth_user_id", self.client.session)


class DashboardTests(WebTestCase):
    def rows(self):
        self.client.force_login(self.student)
        return self.client.get(reverse("web-dashboard")).context["exam_rows"]

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get(reverse("web-dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('web-login')}?next={reverse('web-dashboard')}",
        )

    def test_home_leads_to_the_dashboard(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("web-home"))

        self.assertRedirects(response, reverse("web-dashboard"))

    def test_student_sees_open_exam_with_a_link(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("web-dashboard"))

        self.assertContains(response, "Open exam")
        self.assertContains(response, reverse("web-take-exam", args=[self.exam.id]))

    def test_exam_with_several_questions_is_listed_once(self):
        question = Question.objects.create(
            text="Another",
            question_type=Question.QuestionType.SHORT_ANSWER,
            subject="General",
            topic="General",
            difficulty=Question.Difficulty.EASY,
        )
        ExamQuestion.objects.create(exam=self.exam, question=question, position=2)

        self.assertEqual(len(self.rows()), 1)

    def test_closed_future_and_empty_exams_are_hidden(self):
        self.create_exam("Past", starts=-120, ends=-60)
        self.create_exam("Future", starts=60, ends=120)
        self.create_exam("Empty", with_question=False)

        self.assertEqual([row["exam"] for row in self.rows()], [self.exam])

    def test_state_is_not_started_without_an_attempt(self):
        self.assertEqual(self.rows()[0]["state"], "not_started")

    def test_state_is_in_progress_during_an_attempt(self):
        self.create_attempt()

        self.assertEqual(self.rows()[0]["state"], "in_progress")

    def test_state_is_finished_after_submitting(self):
        self.create_attempt(status=Attempt.Status.SUBMITTED)

        self.assertEqual(self.rows()[0]["state"], "finished")

    def test_state_is_finished_when_the_attempt_has_expired(self):
        self.create_attempt(ends_at=self.now - timedelta(minutes=1))

        self.assertEqual(self.rows()[0]["state"], "finished")

    def test_state_allows_a_granted_reattempt(self):
        self.create_attempt(status=Attempt.Status.SUBMITTED, allow_reattempt=True)

        self.assertEqual(self.rows()[0]["state"], "reattempt")

    def test_running_attempt_stays_listed_after_the_window_closes(self):
        closed = self.create_exam("Closed", starts=-120, ends=-1)
        self.create_attempt(exam=closed)

        rows = {row["exam"]: row["state"] for row in self.rows()}

        self.assertEqual(rows[closed], "in_progress")

    def test_one_students_attempt_does_not_affect_another(self):
        other = User.objects.create_user(
            username="kiran",
            password=PASSWORD,
            role=User.Role.STUDENT,
        )
        Attempt.objects.create(
            exam=self.exam,
            student=other,
            status=Attempt.Status.SUBMITTED,
            ends_at=self.now,
        )

        self.assertEqual(self.rows()[0]["state"], "not_started")

    def test_faculty_sees_no_exam_list(self):
        self.client.force_login(self.faculty)

        response = self.client.get(reverse("web-dashboard"))

        self.assertNotIn("exam_rows", response.context)
        self.assertContains(response, "built yet")


class TakeExamPageTests(WebTestCase):
    def url(self):
        return reverse("web-take-exam", args=[self.exam.id])

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get(self.url())

        self.assertRedirects(response, f"{reverse('web-login')}?next={self.url()}")

    def test_student_gets_the_exam_page(self):
        self.client.force_login(self.student)

        response = self.client.get(self.url())

        self.assertContains(response, "Start exam")

    def test_faculty_is_forbidden(self):
        self.client.force_login(self.faculty)

        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_unknown_exam_is_not_found(self):
        self.client.force_login(self.student)

        response = self.client.get(reverse("web-take-exam", args=[999999]))

        self.assertEqual(response.status_code, 404)

    def assert_page_hidden(self, exam):
        self.client.force_login(self.student)

        response = self.client.get(reverse("web-take-exam", args=[exam.id]))

        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, exam.title, status_code=404)

    def test_future_exam_is_not_found(self):
        self.assert_page_hidden(self.create_exam("Future", starts=60, ends=120))

    def test_closed_exam_is_not_found(self):
        self.assert_page_hidden(self.create_exam("Past", starts=-120, ends=-60))

    def test_exam_without_questions_is_not_found(self):
        self.assert_page_hidden(self.create_exam("Empty", with_question=False))

    def test_expired_attempt_does_not_keep_a_closed_exam_open(self):
        closed = self.create_exam("Past", starts=-120, ends=-60)
        self.create_attempt(exam=closed, ends_at=self.now - timedelta(minutes=1))

        self.assert_page_hidden(closed)

    def test_running_attempt_can_resume_after_the_window_closes(self):
        closed = self.create_exam("Closed", starts=-120, ends=-1)
        self.create_attempt(exam=closed)
        self.client.force_login(self.student)

        response = self.client.get(reverse("web-take-exam", args=[closed.id]))

        self.assertEqual(response.status_code, 200)

    def test_student_can_reopen_an_open_exam_after_submitting(self):
        # The page explains that the attempt is already used.
        self.create_attempt(status=Attempt.Status.SUBMITTED)
        self.client.force_login(self.student)

        self.assertEqual(self.client.get(self.url()).status_code, 200)

    def test_delivery_api_returns_401_once_the_session_ends(self):
        # exam.js shows a log-in link for this response.
        self.client.force_login(self.student)
        attempt = self.create_attempt()
        path = f"/api/exams/{self.exam.id}/attempts/{attempt.id}/timer/"
        self.assertEqual(self.client.get(path).status_code, 200)

        self.client.session.flush()

        self.assertEqual(self.client.get(path).status_code, 401)

    def test_page_does_not_contain_questions_or_answer_keys(self):
        # Questions only load through the delivery API (OEP-SR-004).
        self.client.force_login(self.student)

        response = self.client.get(self.url())

        self.assertNotContains(response, ANSWER_KEY)

    def test_session_login_can_call_the_delivery_api_with_csrf(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.student)
        page = client.get(self.url())
        token = page.context["csrf_token"]
        path = f"/api/exams/{self.exam.id}/start/"

        rejected = client.post(path)
        started = client.post(path, headers={"x-csrftoken": str(token)})

        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(started.status_code, 201)
