from datetime import timedelta
from decimal import Decimal
from unittest import mock
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from exam_delivery.models import Attempt, Response
from courses.models import Course
from exam_delivery.services import ExamNotOpen
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

User = get_user_model()


class ExamDeliveryBaseTestCase(APITestCase):
    def publish(self, exam):
        """Assign the exam to the test course and mark it published."""
        exam.courses.add(self.course)
        exam.status = Exam.Status.PUBLISHED
        exam.save(update_fields=["status"])

    def setUp(self):
        self.now = timezone.now()
        self.student = User.objects.create_user(
            username="student_yash",
            email="student_yash@institution.edu",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
        )
        self.other_student = User.objects.create_user(
            username="student_other",
            email="student_other@institution.edu",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
        )
        self.faculty = User.objects.create_user(
            username="prof_examiner",
            email="prof@institution.edu",
            password="StrongPassword123!",
            role=User.Role.FACULTY,
        )
        self.admin = User.objects.create_user(
            username="admin_delivery",
            email="admin_delivery@institution.edu",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
        )

        self.exam = Exam.objects.create(
            title="Software Engineering Midterm",
            duration_minutes=30,
            availability_start=self.now - timedelta(minutes=10),
            availability_end=self.now + timedelta(hours=2),
            negative_marking_enabled=True,
            negative_marks=Decimal("0.50"),
        )
        # Students sit exams that are published to a course they are in (OEP-F-024).
        self.course = Course.objects.create(code="SE101", name="Software Engineering")
        self.course.students.add(self.student, self.other_student)
        self.publish(self.exam)

        # Questions
        self.q_mcq = Question.objects.create(
            text="What does SRS stand for?",
            question_type=Question.QuestionType.MCQ,
            options=[
                "Software Requirements Specification",
                "System Requirements Standard",
                "Simple Request System",
            ],
            correct_answer="Software Requirements Specification",
            subject="Software Engineering",
            topic="SRS",
            difficulty=Question.Difficulty.EASY,
        )
        self.q_tf = Question.objects.create(
            text="Agile requires exhaustive documentation before coding.",
            question_type=Question.QuestionType.TRUE_FALSE,
            options=["True", "False"],
            correct_answer="False",
            subject="Software Engineering",
            topic="Methodologies",
            difficulty=Question.Difficulty.EASY,
        )
        self.q_fib = Question.objects.create(
            text="The pattern where UI, business logic, and data are separated into three layers is called ____ architecture.",
            question_type=Question.QuestionType.FILL_IN_THE_BLANK,
            options=[],
            correct_answer="three-tier",
            subject="Software Engineering",
            topic="Architecture",
            difficulty=Question.Difficulty.MEDIUM,
        )
        self.q_sa = Question.objects.create(
            text="Explain the purpose of an architectural risk table.",
            question_type=Question.QuestionType.SHORT_ANSWER,
            options=[],
            correct_answer="Identifies risks, severity and planned mitigations.",
            subject="Software Engineering",
            topic="Risk Management",
            difficulty=Question.Difficulty.HARD,
        )

        ExamQuestion.objects.create(exam=self.exam, question=self.q_mcq, position=1, marks=2)
        ExamQuestion.objects.create(exam=self.exam, question=self.q_tf, position=2, marks=1)
        ExamQuestion.objects.create(exam=self.exam, question=self.q_fib, position=3, marks=2)
        ExamQuestion.objects.create(exam=self.exam, question=self.q_sa, position=4, marks=5)


class ExamDeliveryTimerTests(ExamDeliveryBaseTestCase):
    """TC-Deliver-01: Exam screen with server-synced countdown timer (OEP-F-030)."""

    def test_student_starts_exam_and_receives_server_synced_timer(self):
        self.client.force_authenticate(user=self.student)
        url = f"/api/exams/{self.exam.id}/start/"
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data

        self.assertIn("attempt_id", data)
        self.assertIn("ends_at", data)
        self.assertIn("remaining_seconds", data)
        self.assertIn("server_time", data)
        self.assertTrue(data["is_new"])

        # Remaining seconds matches 30 minutes (approx 1800s)
        self.assertGreaterEqual(data["remaining_seconds"], 1790)
        self.assertLessEqual(data["remaining_seconds"], 1800)

        # Questions are served without correct answers (OEP-SR-004)
        questions = data["questions"]
        self.assertEqual(len(questions), 4)
        for q in questions:
            self.assertNotIn("correct_answer", q)
            self.assertNotIn("Software Requirements Specification", str(q.get("correct_answer", "")))

    def test_exam_cannot_be_started_before_availability_window_opens(self):
        future_exam = Exam.objects.create(
            title="Future Exam",
            duration_minutes=30,
            availability_start=self.now + timedelta(hours=1),
            availability_end=self.now + timedelta(hours=2),
        )
        ExamQuestion.objects.create(exam=future_exam, question=self.q_mcq, position=1, marks=2)

        self.client.force_authenticate(user=self.student)
        response = self.client.post(f"/api/exams/{future_exam.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "This exam is not open.")

    def test_exam_cannot_be_started_after_availability_window_closes(self):
        past_exam = Exam.objects.create(
            title="Past Exam",
            duration_minutes=30,
            availability_start=self.now - timedelta(hours=3),
            availability_end=self.now - timedelta(hours=1),
        )
        ExamQuestion.objects.create(exam=past_exam, question=self.q_mcq, position=1, marks=2)

        self.client.force_authenticate(user=self.student)
        response = self.client.post(f"/api/exams/{past_exam.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["detail"], "This exam is not open.")

    def test_timer_status_endpoint_returns_accurate_remaining_time(self):
        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        timer_res = self.client.get(f"/api/exams/{self.exam.id}/attempts/{attempt_id}/timer/")
        self.assertEqual(timer_res.status_code, status.HTTP_200_OK)
        self.assertEqual(timer_res.data["attempt_id"], attempt_id)
        self.assertFalse(timer_res.data["is_expired"])
        self.assertGreater(timer_res.data["remaining_seconds"], 1700)

    def test_ends_at_capped_by_exam_availability_end_if_shorter(self):
        # Exam ends in 10 minutes, but duration is 60 minutes
        tight_exam = Exam.objects.create(
            title="Tight Exam",
            duration_minutes=60,
            availability_start=self.now - timedelta(minutes=5),
            availability_end=self.now + timedelta(minutes=10),
        )
        ExamQuestion.objects.create(exam=tight_exam, question=self.q_mcq, position=1, marks=2)
        self.publish(tight_exam)

        self.client.force_authenticate(user=self.student)
        res = self.client.post(f"/api/exams/{tight_exam.id}/start/")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Remaining time should be capped at around 10 minutes (600s), not 60 minutes (3600s)
        self.assertLessEqual(res.data["remaining_seconds"], 600)


class QuestionNavigationAndFlagTests(ExamDeliveryBaseTestCase):
    """TC-Deliver-02: Question navigation and flag for review (OEP-F-031)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.student)
        res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        self.attempt_id = res.data["attempt_id"]

    def test_flag_question_for_review_toggles_state(self):
        url = f"/api/exams/{self.exam.id}/attempts/{self.attempt_id}/questions/{self.q_mcq.id}/flag/"

        # Toggle flag on
        res1 = self.client.post(url, {"is_flagged": True}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertTrue(res1.data["is_flagged"])

        # Toggle flag off
        res2 = self.client.post(url, {"is_flagged": False}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertFalse(res2.data["is_flagged"])

    def test_question_navigator_reports_answered_and_flagged_states(self):
        nav_url = f"/api/exams/{self.exam.id}/attempts/{self.attempt_id}/navigator/"
        res_initial = self.client.get(nav_url)
        self.assertEqual(res_initial.status_code, status.HTTP_200_OK)
        self.assertEqual(res_initial.data["total_questions"], 4)
        self.assertEqual(res_initial.data["answered_count"], 0)
        self.assertEqual(res_initial.data["flagged_count"], 0)

        # Flag question 1, answer question 2
        self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{self.attempt_id}/questions/{self.q_mcq.id}/flag/",
            {"is_flagged": True},
            format="json",
        )
        self.client.put(
            f"/api/exams/{self.exam.id}/attempts/{self.attempt_id}/autosave/",
            {"responses": [{"question_id": self.q_tf.id, "submitted_answer": "False"}]},
            format="json",
        )

        res_updated = self.client.get(nav_url)
        self.assertEqual(res_updated.status_code, status.HTTP_200_OK)
        self.assertEqual(res_updated.data["answered_count"], 1)
        self.assertEqual(res_updated.data["flagged_count"], 1)

        questions = {q["question_id"]: q for q in res_updated.data["questions"]}
        self.assertTrue(questions[self.q_mcq.id]["is_flagged"])
        self.assertFalse(questions[self.q_mcq.id]["is_answered"])

        self.assertFalse(questions[self.q_tf.id]["is_flagged"])
        self.assertTrue(questions[self.q_tf.id]["is_answered"])

    def test_navigator_positions_match_shuffled_exam_paper(self):
        detail_url = f"/api/exams/{self.exam.id}/attempts/{self.attempt_id}/"
        nav_url = f"/api/exams/{self.exam.id}/attempts/{self.attempt_id}/navigator/"

        detail_res = self.client.get(detail_url)
        nav_res = self.client.get(nav_url)

        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(nav_res.status_code, status.HTTP_200_OK)

        paper_positions = {
            q["question_id"]: q["position"]
            for q in detail_res.data["questions"]
        }
        navigator_positions = {
            q["question_id"]: q["position"]
            for q in nav_res.data["questions"]
        }

        self.assertEqual(paper_positions, navigator_positions)

    def test_two_students_receive_independently_shuffled_papers(self):
        first_detail_url = (
            f"/api/exams/{self.exam.id}/attempts/{self.attempt_id}/"
        )
        first_response = self.client.get(first_detail_url)
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.other_student)
        second_start = self.client.post(
            f"/api/exams/{self.exam.id}/start/"
        )
        self.assertEqual(
            second_start.status_code,
            status.HTTP_201_CREATED,
        )

        second_attempt_id = second_start.data["attempt_id"]
        second_detail_url = (
            f"/api/exams/{self.exam.id}/attempts/{second_attempt_id}/"
        )
        second_response = self.client.get(second_detail_url)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)

        first_questions = first_response.data["questions"]
        second_questions = second_response.data["questions"]

        first_order = [
            question["question_id"] for question in first_questions
        ]
        second_order = [
            question["question_id"] for question in second_questions
        ]

        self.assertCountEqual(first_order, second_order)
        self.assertNotEqual(first_order, second_order)

        first_mcq = next(
            q for q in first_questions
            if q["question_id"] == self.q_mcq.id
        )
        second_mcq = next(
            q for q in second_questions
            if q["question_id"] == self.q_mcq.id
        )

        self.assertCountEqual(
            first_mcq["options"],
            second_mcq["options"],
        )

        # The same attempt must retain its paper after refresh.
        self.client.force_authenticate(user=self.student)
        refreshed_response = self.client.get(first_detail_url)
        self.assertEqual(
            refreshed_response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            first_questions,
            refreshed_response.data["questions"],
        )

class AutoSubmitTimeoutTests(ExamDeliveryBaseTestCase):
    """TC-Deliver-03: Auto-submit on timeout (OEP-F-032)."""

    def test_auto_submit_triggers_when_timer_expires(self):
        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        attempt = Attempt.objects.get(id=attempt_id)
        # Advance attempt ends_at into the past to simulate timeout expiry
        attempt.ends_at = timezone.now() - timedelta(seconds=5)
        attempt.save()

        # Any read / timer / autosave check immediately detects timeout and auto-submits
        detail_res = self.client.get(f"/api/exams/{self.exam.id}/attempts/{attempt_id}/")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_res.data["status"], Attempt.Status.SUBMITTED)
        self.assertEqual(detail_res.data["submission_reason"], Attempt.SubmissionReason.TIMEOUT)

    def test_no_answers_can_be_changed_after_timeout_expiry(self):
        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        attempt = Attempt.objects.get(id=attempt_id)
        attempt.ends_at = timezone.now() - timedelta(seconds=10)
        attempt.save()

        # Autosave attempt should be rejected with 410 Gone
        save_res = self.client.put(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/autosave/",
            {"responses": [{"question_id": self.q_mcq.id, "submitted_answer": "Software Requirements Specification"}]},
            format="json",
        )
        self.assertEqual(save_res.status_code, status.HTTP_410_GONE)


class ManualSubmitTests(ExamDeliveryBaseTestCase):
    """TC-Deliver-04: Manual submit before time limit (OEP-F-033, OEP-F-040)."""

    def test_manual_submit_closes_attempt_and_auto_grades_objective_answers(self):
        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        submit_payload = {
            "reason": "manual",
            "responses": [
                {
                    "question_id": self.q_mcq.id,
                    "submitted_answer": "Software Requirements Specification",  # Correct: +2 marks
                },
                {
                    "question_id": self.q_tf.id,
                    "submitted_answer": "True",  # Incorrect (correct is False): -0.50 marks
                },
                {
                    "question_id": self.q_fib.id,
                    "submitted_answer": "three-tier",  # Correct: +2 marks
                },
                {
                    "question_id": self.q_sa.id,
                    "submitted_answer": "A risk management table.",  # Subjective: pending manual eval
                },
            ],
        }

        submit_res = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/",
            submit_payload,
            format="json",
        )
        self.assertEqual(submit_res.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_res.data["status"], "submitted")
        self.assertEqual(submit_res.data["reason"], "MANUAL")

        attempt = Attempt.objects.get(id=attempt_id)
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        self.assertEqual(attempt.submission_reason, Attempt.SubmissionReason.MANUAL)
        self.assertIsNotNone(attempt.submitted_at)

        # Expected objective score: 2 (q1) - 0.5 (q2) + 2 (q3) = 3.50
        self.assertEqual(attempt.objective_score, Decimal("3.50"))
        # Subjective question exists, so overall grading is not yet complete
        self.assertFalse(attempt.is_graded)

    def test_all_objective_exam_is_marked_graded_immediately_on_submit(self):
        obj_exam = Exam.objects.create(
            title="Objective Only Exam",
            duration_minutes=15,
            availability_start=self.now - timedelta(minutes=5),
            availability_end=self.now + timedelta(hours=1),
        )
        ExamQuestion.objects.create(exam=obj_exam, question=self.q_mcq, position=1, marks=2)
        self.publish(obj_exam)
        ExamQuestion.objects.create(exam=obj_exam, question=self.q_tf, position=2, marks=1)

        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/exams/{obj_exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        submit_res = self.client.post(
            f"/api/exams/{obj_exam.id}/attempts/{attempt_id}/submit/",
            {
                "reason": "manual",
                "responses": [
                    {"question_id": self.q_mcq.id, "submitted_answer": "Software Requirements Specification"},
                    {"question_id": self.q_tf.id, "submitted_answer": "False"},
                ],
            },
            format="json",
        )
        self.assertEqual(submit_res.status_code, status.HTTP_200_OK)

        attempt = Attempt.objects.get(id=attempt_id)
        self.assertTrue(attempt.is_graded)
        self.assertEqual(attempt.objective_score, Decimal("3.00"))
        self.assertEqual(attempt.total_score, Decimal("3.00"))


class SingleAttemptRuleTests(ExamDeliveryBaseTestCase):
    """TC-Deliver-05: Single-attempt rule and faculty re-attempt allowance (OEP-F-034)."""

    def test_student_cannot_attempt_same_exam_twice(self):
        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        # Submit first attempt
        self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/",
            {"reason": "manual"},
            format="json",
        )

        # Attempt to start a second sitting
        second_attempt_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        self.assertEqual(second_attempt_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("A second attempt on the same exam is blocked", second_attempt_res.data["detail"])

    def test_admin_or_faculty_can_explicitly_allow_reattempt(self):
        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/",
            {"reason": "manual"},
            format="json",
        )

        # Student tries to allow reattempt for themselves (forbidden: 403)
        student_allow_res = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/allow-reattempt/"
        )
        self.assertEqual(student_allow_res.status_code, status.HTTP_403_FORBIDDEN)

        # Faculty grants re-attempt
        self.client.force_authenticate(user=self.faculty)
        faculty_allow_res = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/allow-reattempt/"
        )
        self.assertEqual(faculty_allow_res.status_code, status.HTTP_200_OK)
        self.assertTrue(faculty_allow_res.data["allow_reattempt"])

        # Student can now start a new attempt!
        self.client.force_authenticate(user=self.student)
        second_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        self.assertEqual(second_res.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(second_res.data["attempt_id"], attempt_id)


class PeriodicAutosaveTests(ExamDeliveryBaseTestCase):
    """TC-Deliver-06: Periodic auto-save of responses and resume on disconnect (OEP-F-035)."""

    def test_periodic_autosave_preserves_answers_on_disconnect(self):
        self.client.force_authenticate(user=self.student)
        start_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        # Autosave answers
        save_res = self.client.put(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/autosave/",
            {
                "responses": [
                    {
                        "question_id": self.q_mcq.id,
                        "submitted_answer": "Software Requirements Specification",
                        "is_flagged": True,
                    },
                    {
                        "question_id": self.q_fib.id,
                        "submitted_answer": "three-tier",
                        "is_flagged": False,
                    },
                ]
            },
            format="json",
        )
        self.assertEqual(save_res.status_code, status.HTTP_200_OK)
        self.assertEqual(save_res.data["status"], "saved")

        # Simulate disconnect and student reopening exam sitting
        fetch_res = self.client.get(f"/api/exams/{self.exam.id}/attempts/{attempt_id}/")
        self.assertEqual(fetch_res.status_code, status.HTTP_200_OK)

        saved_questions = {q["question_id"]: q for q in fetch_res.data["questions"]}
        self.assertEqual(
            saved_questions[self.q_mcq.id]["submitted_answer"],
            "Software Requirements Specification",
        )
        self.assertTrue(saved_questions[self.q_mcq.id]["is_flagged"])
        self.assertEqual(saved_questions[self.q_fib.id]["submitted_answer"], "three-tier")
        self.assertFalse(saved_questions[self.q_fib.id]["is_flagged"])

    def test_reconnect_restores_answers_and_the_clock_kept_running(self):
        """TC-Deliver-06: a 7-minute disconnect costs time but not answers."""
        self.client.force_authenticate(user=self.student)
        started = timezone.now()
        with patch("django.utils.timezone.now", return_value=started):
            start_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
            attempt_id = start_res.data["attempt_id"]
            self.assertEqual(start_res.data["remaining_seconds"], 30 * 60)
            self.client.put(
                f"/api/exams/{self.exam.id}/attempts/{attempt_id}/autosave/",
                {"responses": [{"question_id": self.q_fib.id, "submitted_answer": "three-tier"}]},
                format="json",
            )

        # The student comes back seven minutes later and presses Resume.
        with patch("django.utils.timezone.now", return_value=started + timedelta(minutes=7)):
            resume_res = self.client.post(f"/api/exams/{self.exam.id}/start/")
            timer_res = self.client.get(f"/api/exams/{self.exam.id}/attempts/{attempt_id}/timer/")

        self.assertEqual(resume_res.status_code, status.HTTP_200_OK)
        self.assertFalse(resume_res.data["is_new"])
        self.assertEqual(resume_res.data["attempt_id"], attempt_id)
        self.assertEqual(resume_res.data["remaining_seconds"], 23 * 60)
        self.assertEqual(timer_res.data["remaining_seconds"], 23 * 60)
        saved = {q["question_id"]: q for q in resume_res.data["questions"]}
        self.assertEqual(saved[self.q_fib.id]["submitted_answer"], "three-tier")

    def test_autosave_reports_remaining_time_so_the_page_can_resync(self):
        self.client.force_authenticate(user=self.student)
        attempt_id = self.client.post(f"/api/exams/{self.exam.id}/start/").data["attempt_id"]

        save_res = self.client.put(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/autosave/",
            {"responses": [{"question_id": self.q_fib.id, "submitted_answer": "three-tier"}]},
            format="json",
        )

        self.assertIn("saved_at", save_res.data)
        self.assertGreater(save_res.data["remaining_seconds"], 29 * 60)
        self.assertLessEqual(save_res.data["remaining_seconds"], 30 * 60)


class ReviewRegressionTests(ExamDeliveryBaseTestCase):
    """Regression coverage for review feedback on exam delivery."""

    def _create_attempt(self, student=None, ends_at=None):
        student = student or self.student
        attempt = Attempt.objects.create(
            exam=self.exam,
            student=student,
            status=Attempt.Status.IN_PROGRESS,
            started_at=self.now - timedelta(minutes=5),
            ends_at=ends_at or self.now + timedelta(minutes=20),
        )
        exam_questions = self.exam.exam_questions.select_related("question").order_by("position")
        Response.objects.bulk_create([
            Response(
                attempt=attempt,
                question=eq.question,
                submitted_answer="",
                is_flagged=False,
            )
            for eq in exam_questions
        ])
        return attempt

    def test_existing_in_progress_attempt_can_resume_after_admission_window_closes(self):
        attempt = self._create_attempt(ends_at=self.now + timedelta(minutes=10))
        self.exam.availability_end = self.now - timedelta(minutes=1)
        self.exam.save(update_fields=["availability_end"])
        self.client.force_authenticate(user=self.student)

        response = self.client.post(f"/api/exams/{self.exam.id}/start/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["attempt_id"], attempt.id)
        self.assertFalse(response.data["is_new"])
        self.assertEqual(Attempt.objects.filter(exam=self.exam, student=self.student).count(), 1)

    def test_expired_attempt_is_committed_as_timeout_when_start_is_rejected(self):
        attempt = self._create_attempt(ends_at=self.now - timedelta(seconds=1))
        self.client.force_authenticate(user=self.student)

        response = self.client.post(f"/api/exams/{self.exam.id}/start/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        self.assertEqual(attempt.submission_reason, Attempt.SubmissionReason.TIMEOUT)

    def test_expired_autosave_commits_timeout_before_returning_error(self):
        attempt = self._create_attempt(ends_at=self.now - timedelta(seconds=1))
        self.client.force_authenticate(user=self.student)

        response = self.client.put(
            f"/api/exams/{self.exam.id}/attempts/{attempt.id}/autosave/",
            {"responses": [{"question_id": self.q_mcq.id, "submitted_answer": "A"}]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        self.assertEqual(attempt.submission_reason, Attempt.SubmissionReason.TIMEOUT)

    def test_manual_submission_after_deadline_is_recorded_as_timeout(self):
        attempt = self._create_attempt(ends_at=self.now - timedelta(seconds=1))
        self.client.force_authenticate(user=self.student)

        response = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt.id}/submit/",
            {"reason": "manual"}, format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        attempt.refresh_from_db()
        self.assertEqual(attempt.submission_reason, Attempt.SubmissionReason.TIMEOUT)

    def test_student_cannot_access_another_students_attempt(self):
        attempt = self._create_attempt(student=self.other_student)
        self.client.force_authenticate(user=self.student)
        response = self.client.get(f"/api/exams/{self.exam.id}/attempts/{attempt.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_cannot_start_or_autosave_student_attempt(self):
        self.client.force_authenticate(user=self.faculty)
        start_response = self.client.post(f"/api/exams/{self.exam.id}/start/")
        self.assertEqual(start_response.status_code, status.HTTP_403_FORBIDDEN)

        attempt = self._create_attempt()
        save_response = self.client.put(
            f"/api/exams/{self.exam.id}/attempts/{attempt.id}/autosave/",
            {"responses": []}, format="json",
        )
        self.assertEqual(save_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_only_role_is_enforced_across_all_sitting_endpoints(self):
        attempt = self._create_attempt()
        self.client.force_authenticate(user=self.faculty)
        base = f"/api/exams/{self.exam.id}/attempts/{attempt.id}"
        requests = [
            self.client.get(f"{base}/"),
            self.client.get(f"{base}/timer/"),
            self.client.get(f"{base}/navigator/"),
            self.client.put(f"{base}/autosave/", {"responses": []}, format="json"),
            self.client.post(f"{base}/submit/", {}, format="json"),
            self.client.post(
                f"{base}/questions/{self.q_mcq.id}/flag/",
                {"is_flagged": True}, format="json",
            ),
        ]
        self.assertTrue(all(item.status_code == status.HTTP_403_FORBIDDEN for item in requests))

    def test_student_cannot_read_or_mutate_another_students_attempt(self):
        attempt = self._create_attempt(student=self.other_student)
        self.client.force_authenticate(user=self.student)
        base = f"/api/exams/{self.exam.id}/attempts/{attempt.id}"
        requests = [
            self.client.get(f"{base}/"),
            self.client.get(f"{base}/timer/"),
            self.client.get(f"{base}/navigator/"),
            self.client.put(f"{base}/autosave/", {"responses": []}, format="json"),
            self.client.post(f"{base}/submit/", {}, format="json"),
            self.client.post(
                f"{base}/questions/{self.q_mcq.id}/flag/",
                {"is_flagged": True}, format="json",
            ),
        ]
        self.assertTrue(all(item.status_code == status.HTTP_403_FORBIDDEN for item in requests))

    def test_autosave_rejects_question_not_in_attempt(self):
        attempt = self._create_attempt()
        unrelated = Question.objects.create(
            text="Unrelated question", question_type=Question.QuestionType.MCQ,
            options=["A", "B"], correct_answer="A", subject="Other",
            topic="Other", difficulty=Question.Difficulty.EASY,
        )
        self.client.force_authenticate(user=self.student)
        response = self.client.put(
            f"/api/exams/{self.exam.id}/attempts/{attempt.id}/autosave/",
            {"responses": [{"question_id": unrelated.id, "submitted_answer": "A"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reattempt_permission_is_consumed_after_new_attempt_starts(self):
        previous = self._create_attempt()
        previous.status = Attempt.Status.SUBMITTED
        previous.submitted_at = self.now
        previous.submission_reason = Attempt.SubmissionReason.MANUAL
        previous.allow_reattempt = True
        previous.save()

        self.client.force_authenticate(user=self.student)
        response = self.client.post(f"/api/exams/{self.exam.id}/start/")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        previous.refresh_from_db()
        self.assertFalse(previous.allow_reattempt)

        second_response = self.client.post(f"/api/exams/{self.exam.id}/start/")
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.data["attempt_id"], response.data["attempt_id"])

    def test_expired_submission_ignores_late_answers_and_grades_only_pre_saved_answers(self):
        attempt = self._create_attempt(ends_at=self.now - timedelta(minutes=10))
        # Pre-save an answer for q_mcq prior to deadline
        mcq_resp = attempt.responses.get(question=self.q_mcq)
        mcq_resp.submitted_answer = "Software Requirements Specification"  # correct answer
        mcq_resp.save()

        # Late submission sends an answer for q_tf after deadline
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt.id}/submit/",
            {
                "responses": [
                    {"question_id": self.q_tf.id, "submitted_answer": "False"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        self.assertEqual(attempt.submission_reason, Attempt.SubmissionReason.TIMEOUT)

        # q_mcq (pre-saved) was scored
        mcq_resp.refresh_from_db()
        self.assertEqual(mcq_resp.submitted_answer, "Software Requirements Specification")
        self.assertEqual(mcq_resp.marks_obtained, Decimal("2.00"))

        # q_tf (late answer) was ignored and NOT saved or scored
        tf_resp = attempt.responses.get(question=self.q_tf)
        self.assertEqual(tf_resp.submitted_answer, "")
        self.assertEqual(tf_resp.marks_obtained, Decimal("0.00"))
        self.assertEqual(attempt.objective_score, Decimal("2.00"))

    def test_client_cannot_forge_timeout_reason_on_ontime_submission(self):
        attempt = self._create_attempt(ends_at=self.now + timedelta(minutes=30))
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt.id}/submit/",
            {
                "reason": "timeout",
                "responses": [
                    {"question_id": self.q_mcq.id, "submitted_answer": "Software Requirements Specification"}
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, Attempt.Status.SUBMITTED)
        self.assertEqual(attempt.submission_reason, Attempt.SubmissionReason.MANUAL)
        self.assertEqual(attempt.objective_score, Decimal("2.00"))

    def test_submit_rejects_question_not_in_attempt(self):
        attempt = self._create_attempt(ends_at=self.now + timedelta(minutes=30))
        unrelated = Question.objects.create(
            text="Unrelated question", question_type=Question.QuestionType.MCQ,
            options=["A", "B"], correct_answer="A", subject="Other",
            topic="Other", difficulty=Question.Difficulty.EASY,
        )
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt.id}/submit/",
            {"responses": [{"question_id": unrelated.id, "submitted_answer": "A"}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_diagnostics_security_does_not_disclose_database_exceptions(self):
        admin = User.objects.create_user(
            username="test_admin_diag_deliv",
            email="admin_diag_deliv@test.edu",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=admin)
        from unittest.mock import patch
        with patch("exam_delivery.diagnostics.connection.cursor", side_effect=Exception("sensitive_db_password")):
            response = self.client.get("/api/admin/diagnostics/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "degraded")
        self.assertEqual(response.data["database"]["status"], "unreachable")
        self.assertNotIn("sensitive_db_password", str(response.data))


class ConcurrentStartTests(ExamDeliveryBaseTestCase):
    """OEP-F-034: simultaneous Start requests must not create two attempts."""

    def _in_progress(self, **overrides):
        values = dict(
            exam=self.exam,
            student=self.student,
            status=Attempt.Status.IN_PROGRESS,
            started_at=self.now,
            ends_at=self.now + timedelta(minutes=30),
        )
        values.update(overrides)
        return Attempt.objects.create(**values)

    def test_database_rejects_second_in_progress_attempt_for_same_exam_and_student(self):
        self._in_progress()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._in_progress()

        self.assertEqual(Attempt.objects.filter(exam=self.exam, student=self.student).count(), 1)

    def test_constraint_allows_new_attempt_once_previous_one_is_closed(self):
        self._in_progress(status=Attempt.Status.SUBMITTED, submitted_at=self.now)
        self._in_progress()

        self.assertEqual(Attempt.objects.filter(exam=self.exam, student=self.student).count(), 2)

    def test_constraint_does_not_block_other_students_or_other_exams(self):
        self._in_progress()
        self._in_progress(student=self.other_student)
        other_exam = Exam.objects.create(
            title="Another Exam",
            duration_minutes=30,
            availability_start=self.now - timedelta(minutes=10),
            availability_end=self.now + timedelta(hours=2),
        )
        self._in_progress(exam=other_exam)

        self.assertEqual(Attempt.objects.filter(status=Attempt.Status.IN_PROGRESS).count(), 3)

    def test_start_request_that_loses_the_race_resumes_the_winning_attempt(self):
        winner = {}

        def lose_race(**kwargs):
            # Another request commits its attempt after this one passed the
            # check; this request then hits the unique constraint.
            winner["attempt"] = self._in_progress()
            raise IntegrityError("duplicate in-progress attempt")

        self.client.force_authenticate(user=self.student)
        with mock.patch("exam_delivery.services._start_or_resume_locked", side_effect=lose_race):
            response = self.client.post(f"/api/exams/{self.exam.id}/start/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_new"])
        self.assertEqual(response.data["attempt_id"], winner["attempt"].id)
        self.assertEqual(Attempt.objects.filter(exam=self.exam, student=self.student).count(), 1)

    def test_integrity_error_without_a_winning_attempt_is_not_swallowed(self):
        self.client.force_authenticate(user=self.student)
        with mock.patch(
            "exam_delivery.services._start_or_resume_locked",
            side_effect=IntegrityError("unrelated integrity failure"),
        ):
            with self.assertRaises(IntegrityError):
                self.client.post(f"/api/exams/{self.exam.id}/start/")


class TrueFalseOptionsTests(ExamDeliveryBaseTestCase):
    """True/False questions must reach the client with True and False options."""

    def setUp(self):
        super().setUp()
        # Created the way the question-bank API allows: no options stored.
        self.bare_tf = Question.objects.create(
            text="A unit test exercises one small piece of behaviour.",
            question_type=Question.QuestionType.TRUE_FALSE,
            options=[],
            correct_answer="True",
            subject="Software Engineering",
            topic="Testing",
            difficulty=Question.Difficulty.EASY,
        )
        self.tf_exam = Exam.objects.create(
            title="True/False Exam",
            duration_minutes=30,
            availability_start=self.now - timedelta(minutes=10),
            availability_end=self.now + timedelta(hours=2),
        )
        ExamQuestion.objects.create(exam=self.tf_exam, question=self.bare_tf, position=1, marks=1)
        ExamQuestion.objects.create(exam=self.tf_exam, question=self.q_fib, position=2, marks=1)

        # OEP-F-024: this student may sit only published exams assigned to their courses.
        course = Course.objects.create(code="TF101", name="True/False Options Course")
        course.students.add(self.student)
        self.tf_exam.courses.add(course)
        self.tf_exam.status = Exam.Status.PUBLISHED
        self.tf_exam.save(update_fields=["status"])

        self.client.force_authenticate(user=self.student)

    def _options_by_type(self, data):
        return {q["question_type"]: q["options"] for q in data["questions"]}

    def test_start_returns_true_false_options_when_none_are_stored(self):
        response = self.client.post(f"/api/exams/{self.tf_exam.id}/start/")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        options = self._options_by_type(response.data)
        self.assertEqual(options[Question.QuestionType.TRUE_FALSE], ["True", "False"])
        self.assertEqual(options[Question.QuestionType.FILL_IN_THE_BLANK], [])

    def test_resume_and_detail_return_true_false_options_when_none_are_stored(self):
        first = self.client.post(f"/api/exams/{self.tf_exam.id}/start/")
        resumed = self.client.post(f"/api/exams/{self.tf_exam.id}/start/")
        detail = self.client.get(
            f"/api/exams/{self.tf_exam.id}/attempts/{first.data['attempt_id']}/"
        )

        self.assertEqual(resumed.status_code, status.HTTP_200_OK)
        self.assertFalse(resumed.data["is_new"])
        for payload in (resumed.data, detail.data):
            self.assertEqual(
                self._options_by_type(payload)[Question.QuestionType.TRUE_FALSE],
                ["True", "False"],
            )

    def test_true_false_options_are_fixed_even_if_stored_options_differ(self):
        self.bare_tf.options = ["true", "false", "maybe"]
        self.bare_tf.save(update_fields=["options"])

        response = self.client.post(f"/api/exams/{self.tf_exam.id}/start/")

        self.assertEqual(
            self._options_by_type(response.data)[Question.QuestionType.TRUE_FALSE],
            ["True", "False"],
        )

    def test_true_false_answer_selected_from_options_is_graded(self):
        start = self.client.post(f"/api/exams/{self.tf_exam.id}/start/")
        attempt_id = start.data["attempt_id"]

        submit = self.client.post(
            f"/api/exams/{self.tf_exam.id}/attempts/{attempt_id}/submit/",
            {"responses": [{"question_id": self.bare_tf.id, "submitted_answer": "True"}]},
            format="json",
        )

        self.assertEqual(submit.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(submit.data["objective_score"]), Decimal("1.00"))
