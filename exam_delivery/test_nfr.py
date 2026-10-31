import concurrent.futures
import time
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
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
        """Exercise 200 concurrent exam starts on a row-locking database backend."""
        if connection.vendor == "sqlite":
            self.skipTest(
                "SQLite's shared in-memory test database cannot safely service this "
                "200-writer concurrency test; run it against the production database backend."
            )

        students = [
            User.objects.create_user(
                username=f"perf_user_{i}",
                password="StrongPassword123!",
                role=User.Role.STUDENT,
            )
            for i in range(200)
        ]

        def start_exam(student):
            # Django database connections are thread-local; do not share clients
            # or connections between worker threads.
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user=student)
                started = time.perf_counter()
                response = client.post(f"/api/exams/{self.exam.id}/start/")
                elapsed = time.perf_counter() - started
                return response.status_code, elapsed
            finally:
                close_old_connections()

        worker_count = min(50, len(students))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(start_exam, students))

        statuses = [code for code, _ in results]
        latencies = sorted(elapsed for _, elapsed in results)
        failures = [code for code in statuses if code != status.HTTP_201_CREATED]
        self.assertEqual(len(results), 200)
        self.assertFalse(failures, f"Exam-start requests failed with statuses: {failures}")

        def percentile(values, percentile_value):
            index = max(0, min(len(values) - 1, int((percentile_value / 100) * len(values)) - 1))
            return values[index]

        p50 = percentile(latencies, 50)
        p90 = percentile(latencies, 90)
        p99 = percentile(latencies, 99)
        error_rate = len(failures) / len(results)
        self.assertEqual(error_rate, 0.0)
        if connection.vendor != "sqlite":
            self.assertLessEqual(p90, 2.0, f"P90 exam-start latency was {p90:.4f}s")
        else:
            # SQLite serializes concurrent writes; its timing is useful as a
            # smoke-test measurement, not as evidence for the production SLA.
            print("PERF_NOTE SQLite backend detected; P90 SLA assertion requires the production database backend.")

        # Store actual run measurements in test output for reproducible reports.
        print(
            "PERF_METRICS "
            f"requests={len(results)} workers={worker_count} "
            f"p50={p50:.6f}s p90={p90:.6f}s p99={p99:.6f}s "
            f"error_rate={error_rate:.4%}"
        )

    def test_tc_rel_01_reliability_no_response_loss_on_disconnect(self):
        """TC-Rel-01: Persistence across client-session replacement; not a network fault test."""
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

        # 3. Simulate client-session replacement. This does not interrupt the network.
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

    def test_tc_ops_01_availability_100_health_probe_simulation(self):
        """Run 100 consecutive probes; this is not an uptime/SLA measurement."""
        client = APIClient()
        client.force_authenticate(user=self.admin)
        successful_probes = 0
        total_probes = 100

        for _ in range(total_probes):
            response = client.get("/api/admin/diagnostics/")
            if response.status_code == status.HTTP_200_OK and response.data.get("status") == "healthy":
                successful_probes += 1

        observed_probe_success = (successful_probes / total_probes) * 100.0
        self.assertGreaterEqual(
            observed_probe_success,
            99.0,
            f"Successful probe rate was {observed_probe_success:.1f}%.",
        )
        print(
            "AVAILABILITY_PROBE_METRICS "
            f"successful={successful_probes} total={total_probes} "
            f"success_rate={observed_probe_success:.2f}% "
            "observation_period=single_test_run"
        )
