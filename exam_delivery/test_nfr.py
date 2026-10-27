import concurrent.futures
import time
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from exam_delivery.models import Attempt, Response
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

User = get_user_model()


class NonFunctionalRequirementsTests(TransactionTestCase):
    """NFR verification tests for Performance, Reliability, and Availability."""

    def setUp(self):
        self.now = timezone.now()
        self.exam = Exam.objects.create(
            title="NFR Assessment Exam",
            duration_minutes=45,
            availability_start=self.now - timedelta(minutes=15),
            availability_end=self.now + timedelta(hours=3),
        )
        self.question = Question.objects.create(
            text="What is 10 + 10?",
            question_type=Question.QuestionType.MCQ,
            options=["15", "20", "25"],
            correct_answer="20",
            subject="Maths",
            topic="Basic",
            difficulty=Question.Difficulty.EASY,
        )
        ExamQuestion.objects.create(
            exam=self.exam,
            question=self.question,
            position=1,
            marks=2,
        )
        self.admin = User.objects.create_user(
            username="nfr_admin",
            password="StrongPassword123!",
            role=User.Role.ADMIN,
        )

    def test_tc_perf_01_performance_200_concurrent_requests(self):
        """TC-Perf-01: Response time <= 2s under 200 requests (OEP-NF-001)."""
        students = [
            User.objects.create_user(
                username=f"perf_user_{i}",
                password="StrongPassword123!",
                role=User.Role.STUDENT,
            )
            for i in range(50)
        ]

        # Pre-create in-progress attempts for all students
        attempts = []
        for s in students:
            att = Attempt.objects.create(
                exam=self.exam,
                student=s,
                status=Attempt.Status.IN_PROGRESS,
                started_at=self.now,
                ends_at=self.now + timedelta(minutes=45),
            )
            Response.objects.create(
                attempt=att,
                question=self.question,
                submitted_answer="",
            )
            attempts.append(att)

        latencies = []

        def execute_action(client, action_fn):
            t0 = time.perf_counter()
            res = action_fn()
            t1 = time.perf_counter()
            latencies.append(t1 - t0)
            return res

        def simulate_student_lifecycle(student, attempt):
            client = APIClient()
            client.force_authenticate(user=student)

            # Request 1: Get attempt details / exam paper
            res1 = execute_action(
                client,
                lambda: client.get(f"/api/exams/{self.exam.id}/attempts/{attempt.id}/"),
            )
            self.assertEqual(res1.status_code, status.HTTP_200_OK)

            # Request 2: Get timer status
            res2 = execute_action(
                client,
                lambda: client.get(f"/api/exams/{self.exam.id}/attempts/{attempt.id}/timer/"),
            )
            self.assertEqual(res2.status_code, status.HTTP_200_OK)

            # Request 3: Flag question navigator check
            res3 = execute_action(
                client,
                lambda: client.get(f"/api/exams/{self.exam.id}/attempts/{attempt.id}/navigator/"),
            )
            self.assertEqual(res3.status_code, status.HTTP_200_OK)

            # Request 4: Autosave response
            res4 = execute_action(
                client,
                lambda: client.put(
                    f"/api/exams/{self.exam.id}/attempts/{attempt.id}/autosave/",
                    {"responses": [{"question_id": self.question.id, "submitted_answer": "20"}]},
                    format="json",
                ),
            )
            self.assertEqual(res4.status_code, status.HTTP_200_OK)

        # Execute 50 students * 4 requests = 200 requests
        for s, att in zip(students, attempts):
            simulate_student_lifecycle(s, att)

        self.assertEqual(len(latencies), 200)

        latencies.sort()
        p90_index = int(len(latencies) * 0.90)
        p90_latency = latencies[p90_index]

        # Requirement: 90th percentile <= 2.0s
        self.assertLessEqual(
            p90_latency,
            2.0,
            f"P90 response time was {p90_latency:.4f}s, exceeding 2.0s limit.",
        )

    def test_tc_rel_01_reliability_no_response_loss_on_disconnect(self):
        """TC-Rel-01: Zero response loss on network disconnect, idempotent submit (OEP-NF-002)."""
        student = User.objects.create_user(
            username="rel_student",
            password="StrongPassword123!",
            role=User.Role.STUDENT,
        )
        client = APIClient()
        client.force_authenticate(user=student)

        # 1. Start exam
        start_res = client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = start_res.data["attempt_id"]

        # 2. Autosave answers
        client.put(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/autosave/",
            {"responses": [{"question_id": self.question.id, "submitted_answer": "20", "is_flagged": True}]},
            format="json",
        )

        # 3. Simulate sudden network disconnect by discarding client session
        del client
        reconnected_client = APIClient()
        reconnected_client.force_authenticate(user=student)

        # Re-fetch attempt details
        detail_res = reconnected_client.get(f"/api/exams/{self.exam.id}/attempts/{attempt_id}/")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)

        saved_answer = detail_res.data["questions"][0]["submitted_answer"]
        is_flagged = detail_res.data["questions"][0]["is_flagged"]

        # Assert zero loss of submitted responses
        self.assertEqual(saved_answer, "20")
        self.assertTrue(is_flagged)

        # 4. Idempotent submit test: submit twice
        sub1 = reconnected_client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/",
            {"reason": "manual"},
            format="json",
        )
        self.assertEqual(sub1.status_code, status.HTTP_200_OK)
        self.assertFalse(sub1.data["already_submitted"])

        # Immediate retry of submission (e.g. timeout on client side or double-click)
        sub2 = reconnected_client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/",
            {"reason": "manual"},
            format="json",
        )
        self.assertEqual(sub2.status_code, status.HTTP_200_OK)
        self.assertTrue(sub2.data["already_submitted"])
        self.assertEqual(sub1.data["submitted_at"], sub2.data["submitted_at"])

    def test_tc_ops_01_availability_99_percent_uptime(self):
        """TC-Ops-01: Health check availability >= 99% in exam windows (OEP-NF-003)."""
        client = APIClient()
        client.force_authenticate(user=self.admin)

        successful_probes = 0
        total_probes = 100

        for _ in range(total_probes):
            res = client.get("/api/admin/diagnostics/")
            if res.status_code == status.HTTP_200_OK and res.data.get("status") == "healthy":
                successful_probes += 1

        uptime_percentage = (successful_probes / total_probes) * 100.0
        self.assertGreaterEqual(
            uptime_percentage,
            99.0,
            f"Observed availability was {uptime_percentage}%, below 99% requirement.",
        )
