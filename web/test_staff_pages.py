"""Web pages for grading, results, class reports and the audit log."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.audit import EVENT_EVALUATION, EVENT_LOGIN, record_audit_event
from evaluation.testing import EvaluationWorldMixin
from exam_delivery.models import Attempt


class PageTestCase(EvaluationWorldMixin, TestCase):
    def setUp(self):
        self.create_world()
        self.attempt = self.make_attempt(self.student)
        self.resp_a = self.response_for(self.attempt, self.short_a)
        self.resp_b = self.response_for(self.attempt, self.short_b)

    def grade(self, response, marks, feedback=""):
        return self.client.post(
            reverse("web-grade-response", args=[response.id]),
            {"marks": marks, "feedback": feedback},
            follow=True,
        )


class AccessTests(PageTestCase):
    STAFF_PAGES = ["web-grading", "web-reports"]

    def test_anonymous_visitors_are_sent_to_login(self):
        for name in self.STAFF_PAGES + ["web-results", "web-audit-log"]:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("web-login")))

    def test_students_cannot_open_staff_pages(self):
        self.client.force_login(self.student)
        for name in self.STAFF_PAGES + ["web-audit-log"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("web-report", args=[self.exam.id])).status_code, 403
        )

    def test_students_cannot_grade(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("web-grade-response", args=[self.resp_a.id]), {"marks": "5"}
        )
        self.assertEqual(response.status_code, 403)
        self.resp_a.refresh_from_db()
        self.assertIsNone(self.resp_a.marks_obtained)

    def test_faculty_cannot_open_audit_log_or_results(self):
        self.client.force_login(self.faculty)
        self.assertEqual(self.client.get(reverse("web-audit-log")).status_code, 403)
        self.assertEqual(self.client.get(reverse("web-results")).status_code, 403)

    def test_admin_can_open_every_staff_page(self):
        self.client.force_login(self.admin)
        for name in self.STAFF_PAGES + ["web-audit-log"]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class GradingPageTests(PageTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.faculty)

    def test_queue_lists_pending_answers_with_student_and_question(self):
        page = self.client.get(reverse("web-grading"))

        self.assertContains(page, "Mixed Exam")
        self.assertContains(page, "Explain polymorphism.")
        self.assertContains(page, "The student&#x27;s written answer.")
        self.assertContains(page, "Marks (out of 5)")
        # Objective questions are never in the queue.
        self.assertNotContains(page, "What does CPU stand for?")
        # The answer key is never shown to graders here.
        self.assertNotContains(page, "model answer A")

    def test_grading_saves_marks_feedback_and_leaves_the_queue(self):
        page = self.grade(self.resp_a, "4", "Clear example")

        self.resp_a.refresh_from_db()
        self.assertEqual(self.resp_a.marks_obtained, Decimal("4.00"))
        self.assertEqual(self.resp_a.feedback, "Clear example")
        self.assertEqual(self.resp_a.evaluated_by, self.faculty)
        self.assertContains(page, "Saved 4.00 / 5 marks.")
        self.assertContains(page, "1 more answer(s)")
        self.assertNotContains(page, "Explain polymorphism.")

    def test_grading_the_last_answer_finalizes_the_attempt(self):
        self.grade(self.resp_a, "4")
        page = self.grade(self.resp_b, "3")

        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.is_graded)
        self.assertEqual(self.attempt.total_score, Decimal("9.00"))
        self.assertContains(page, "total score 9.00")
        self.assertContains(page, "Nothing to grade.")

    def test_marks_above_the_maximum_are_refused(self):
        page = self.grade(self.resp_a, "6")

        self.resp_a.refresh_from_db()
        self.assertIsNone(self.resp_a.marks_obtained)
        self.assertContains(page, "Not saved: Marks cannot exceed")

    def test_non_numeric_marks_are_refused(self):
        for bad in ["abc", "", "NaN"]:
            with self.subTest(marks=bad):
                page = self.grade(self.resp_a, bad)
                self.assertContains(page, "Enter the marks as a number")
        self.resp_a.refresh_from_db()
        self.assertIsNone(self.resp_a.marks_obtained)

    def test_exam_filter_is_kept_after_grading(self):
        response = self.client.post(
            reverse("web-grade-response", args=[self.resp_a.id]),
            {"marks": "1", "exam_id": str(self.exam.id)},
        )
        self.assertRedirects(
            response, f"{reverse('web-grading')}?exam_id={self.exam.id}"
        )

    def test_grading_requires_post(self):
        response = self.client.get(reverse("web-grade-response", args=[self.resp_a.id]))
        self.assertEqual(response.status_code, 405)


class ResultsPageTests(PageTestCase):
    def finish_grading(self):
        self.client.force_login(self.faculty)
        self.grade(self.resp_a, "4", "Good use of an example")
        self.grade(self.resp_b, "3")
        self.client.force_login(self.student)

    def test_ungraded_attempt_shows_as_waiting(self):
        self.client.force_login(self.student)
        page = self.client.get(reverse("web-results"))

        self.assertContains(page, "Waiting for grading")
        self.assertContains(page, "Mixed Exam")
        self.assertNotContains(page, "View scorecard")

    def test_ungraded_scorecard_redirects_with_a_message(self):
        self.client.force_login(self.student)
        page = self.client.get(
            reverse("web-scorecard", args=[self.attempt.id]), follow=True
        )
        self.assertRedirects(page, reverse("web-results"))
        self.assertContains(page, "isn&#x27;t ready yet")

    def test_graded_attempt_shows_score_and_feedback(self):
        self.finish_grading()

        listing = self.client.get(reverse("web-results"))
        self.assertContains(listing, "9.00 / 10")
        self.assertContains(listing, "View scorecard")

        card = self.client.get(reverse("web-scorecard", args=[self.attempt.id]))
        self.assertContains(card, "Scorecard: Mixed Exam")
        self.assertContains(card, "Good use of an example")
        self.assertContains(card, "4.00 / 5")
        # Answer keys are never shown to students (OEP-SR-004).
        self.assertNotContains(card, "model answer A")

    def test_students_cannot_see_another_students_scorecard(self):
        self.finish_grading()
        self.client.force_login(self.other_student)

        response = self.client.get(reverse("web-scorecard", args=[self.attempt.id]))
        self.assertEqual(response.status_code, 404)

    def test_dashboard_links_to_results(self):
        self.client.force_login(self.student)
        page = self.client.get(reverse("web-dashboard"))
        self.assertContains(page, reverse("web-results"))


class ReportPageTests(PageTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.faculty)

    def test_report_list_shows_counts(self):
        page = self.client.get(reverse("web-reports"))
        self.assertContains(page, "Mixed Exam")
        self.assertContains(page, reverse("web-report", args=[self.exam.id]))

    def test_report_shows_pending_then_scores_after_grading(self):
        url = reverse("web-report", args=[self.exam.id])

        page = self.client.get(url)
        self.assertContains(page, "1 student still has answers waiting")

        self.grade(self.resp_a, "4")
        self.grade(self.resp_b, "3")
        page = self.client.get(url)
        self.assertNotContains(page, "waiting to be graded")
        self.assertContains(page, "eval_student")
        self.assertContains(page, "9.00 / 10")
        self.assertContains(page, "90.00")

    def test_report_links_to_both_exports_and_they_download(self):
        page = self.client.get(reverse("web-report", args=[self.exam.id]))
        for fmt, content_type in [
            ("xlsx", "spreadsheetml"),
            ("pdf", "application/pdf"),
        ]:
            with self.subTest(format=fmt):
                url = f"{reverse('report-exam-export', args=[self.exam.id])}?export_format={fmt}"
                self.assertContains(page, url)
                download = self.client.get(url)
                self.assertEqual(download.status_code, 200)
                self.assertIn(content_type, download["Content-Type"])
                self.assertIn("attachment", download["Content-Disposition"])

    def test_unknown_exam_is_404(self):
        self.assertEqual(
            self.client.get(reverse("web-report", args=[999999])).status_code, 404
        )


class AuditLogPageTests(PageTestCase):
    def setUp(self):
        super().setUp()
        record_audit_event(EVENT_LOGIN, actor=self.student, description="Logged in")
        record_audit_event(
            EVENT_EVALUATION, actor=self.faculty, description="Subjective response evaluated"
        )
        self.client.force_login(self.admin)

    def test_lists_entries_newest_first(self):
        page = self.client.get(reverse("web-audit-log")).content.decode()
        self.assertIn("Subjective response evaluated", page)
        self.assertIn("Logged in", page)
        self.assertLess(
            page.index("Subjective response evaluated"), page.index("Logged in")
        )

    def test_filters_by_event(self):
        page = self.client.get(reverse("web-audit-log"), {"event_type": EVENT_LOGIN})
        self.assertContains(page, "Logged in")
        self.assertNotContains(page, "Subjective response evaluated")

    def test_unknown_event_filter_is_404(self):
        response = self.client.get(reverse("web-audit-log"), {"event_type": "nope"})
        self.assertEqual(response.status_code, 404)


class StaffDashboardTests(PageTestCase):
    def test_faculty_dashboard_links_to_grading_and_reports(self):
        self.client.force_login(self.faculty)
        page = self.client.get(reverse("web-dashboard"))

        self.assertContains(page, "2 answers waiting to be graded.")
        self.assertContains(page, reverse("web-grading"))
        self.assertContains(page, reverse("web-reports"))
        self.assertNotContains(page, reverse("web-audit-log"))

    def test_admin_dashboard_also_links_to_audit_log_and_health(self):
        self.client.force_login(self.admin)
        page = self.client.get(reverse("web-dashboard"))

        self.assertContains(page, reverse("web-audit-log"))
        self.assertContains(page, reverse("web-system-health"))

    def test_in_progress_attempts_are_not_in_the_grading_queue(self):
        Attempt.objects.all().delete()
        self.make_attempt(self.other_student, status=Attempt.Status.IN_PROGRESS)
        self.client.force_login(self.faculty)

        page = self.client.get(reverse("web-grading"))
        self.assertContains(page, "Nothing to grade.")
