from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from exam_delivery.models import Attempt, Response
from exam_delivery.services import ExamNotOpen
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

User = get_user_model()


class ExamDeliveryBaseTestCase(APITestCase):
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
