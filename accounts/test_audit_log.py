"""OEP-NF-004 / TC-Audit-01: key actions are logged and retained."""

import json
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.audit import record_audit_event
from accounts.audit_models import (
    AuditLog,
    AuditLogImmutable,
    MINIMUM_RETENTION_DAYS,
    retention_days,
)
from exam_management.models import Exam, ExamQuestion
from question_bank.models import Question

User = get_user_model()
AUDIT_URL = "/api/admin/users/audit-logs/"
SECRET_ANSWER = "SECRET-ANSWER-TEXT-12345"


def backdate(entry, days):
    """Make an entry look ``days`` old (the model itself refuses edits)."""
    AuditLog._base_manager.filter(pk=entry.pk).update(
        created_at=timezone.now() - timedelta(days=days)
    )


class AppendOnlyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="audit_user", password="StrongPassword123!", role=User.Role.ADMIN
        )
        self.entry = record_audit_event(
            "test.event", actor=self.user, description="original"
        )

    def test_entry_carries_user_action_and_timestamp(self):
        self.assertEqual(self.entry.actor, self.user)
        self.assertEqual(self.entry.event_type, "test.event")
        self.assertIsNotNone(self.entry.created_at)

    def test_stored_entry_cannot_be_edited(self):
        self.entry.description = "tampered"

        with self.assertRaises(AuditLogImmutable):
            self.entry.save()

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.description, "original")

    def test_stored_entry_cannot_be_deleted(self):
        with self.assertRaises(AuditLogImmutable):
            self.entry.delete()

        self.assertTrue(AuditLog.objects.filter(pk=self.entry.pk).exists())

    def test_bulk_update_and_delete_are_refused(self):
        with self.assertRaises(AuditLogImmutable):
            AuditLog.objects.all().update(description="tampered")
        with self.assertRaises(AuditLogImmutable):
            AuditLog.objects.all().delete()
        with self.assertRaises(AuditLogImmutable):
            AuditLog.objects.bulk_update([self.entry], ["description"])

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.description, "original")

    def test_new_entries_can_still_be_added(self):
        record_audit_event("test.another")

        self.assertEqual(AuditLog.objects.count(), 2)


class KeyActionLoggingTests(APITestCase):
    """The four action types: logins, submissions, evaluations, integrity flags."""

    def setUp(self):
        now = timezone.now()
        self.student = User.objects.create_user(
            username="audit_student", password="StrongPassword123!", role=User.Role.STUDENT
        )
        self.other_student = User.objects.create_user(
            username="audit_other", password="StrongPassword123!", role=User.Role.STUDENT
        )
        self.faculty = User.objects.create_user(
            username="audit_faculty", password="StrongPassword123!", role=User.Role.FACULTY
        )
        self.exam = Exam.objects.create(
            title="Audit Exam",
            duration_minutes=30,
            availability_start=now - timedelta(minutes=5),
            availability_end=now + timedelta(hours=1),
        )
        self.question = Question.objects.create(
            text="Explain inheritance.",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="model",
            subject="CS",
            topic="OOP",
            difficulty=Question.Difficulty.EASY,
        )
        ExamQuestion.objects.create(
            exam=self.exam, question=self.question, position=1, marks=5
        )

    def start_and_submit(self):
        self.client.force_authenticate(user=self.student)
        started = self.client.post(f"/api/exams/{self.exam.id}/start/")
        attempt_id = started.data["attempt_id"]
        submitted = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/",
            {"responses": [{"question_id": self.question.id, "submitted_answer": SECRET_ANSWER}]},
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_200_OK)
        return attempt_id

    def test_login_is_logged(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "audit_student", "password": "StrongPassword123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry = AuditLog.objects.get(event_type="login.success")
        self.assertEqual(entry.actor, self.student)

    def test_submission_is_logged(self):
        attempt_id = self.start_and_submit()

        entry = AuditLog.objects.get(event_type="exam.submitted")

        self.assertEqual(entry.actor, self.student)
        self.assertEqual(entry.metadata["attempt_id"], attempt_id)
        self.assertEqual(entry.metadata["exam_id"], self.exam.id)

    def test_repeated_submission_is_logged_once(self):
        attempt_id = self.start_and_submit()

        self.client.post(f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/")

        self.assertEqual(AuditLog.objects.filter(event_type="exam.submitted").count(), 1)

    def test_evaluation_changes_are_logged(self):
        attempt_id = self.start_and_submit()
        from exam_delivery.models import Response as AnswerRow
        answer = AnswerRow.objects.get(attempt_id=attempt_id, question=self.question)
        self.client.force_authenticate(user=self.faculty)

        self.client.patch(
            f"/api/evaluation/responses/{answer.id}/", {"marks": "3"}, format="json"
        )
        self.client.patch(
            f"/api/evaluation/responses/{answer.id}/", {"marks": "4.5"}, format="json"
        )

        entries = list(AuditLog.objects.filter(event_type="evaluation.updated").order_by("id"))
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].actor, self.faculty)
        self.assertIsNone(entries[0].metadata["previous_marks"])
        self.assertEqual(entries[0].metadata["marks"], "3.00")
        self.assertEqual(entries[1].metadata["previous_marks"], "3.00")
        self.assertEqual(entries[1].metadata["marks"], "4.50")
        self.assertTrue(entries[1].metadata["regraded"])

    def test_rejected_evaluation_is_not_logged(self):
        attempt_id = self.start_and_submit()
        from exam_delivery.models import Response as AnswerRow
        answer = AnswerRow.objects.get(attempt_id=attempt_id, question=self.question)
        self.client.force_authenticate(user=self.faculty)

        self.client.patch(
            f"/api/evaluation/responses/{answer.id}/", {"marks": "99"}, format="json"
        )

        self.assertFalse(AuditLog.objects.filter(event_type="evaluation.updated").exists())

    def test_reaching_for_another_students_attempt_is_flagged(self):
        attempt_id = self.start_and_submit()
        self.client.force_authenticate(user=self.other_student)

        response = self.client.get(f"/api/exams/{self.exam.id}/attempts/{attempt_id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        entry = AuditLog.objects.get(event_type="integrity.flag")
        self.assertEqual(entry.actor, self.other_student)
        self.assertEqual(entry.metadata["reason"], "foreign_attempt_access")
        self.assertEqual(entry.metadata["attempt_id"], attempt_id)

    def test_submitting_another_students_attempt_is_flagged_and_logged(self):
        attempt_id = self.start_and_submit()
        self.client.force_authenticate(user=self.other_student)

        response = self.client.post(
            f"/api/exams/{self.exam.id}/attempts/{attempt_id}/submit/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            AuditLog.objects.filter(
                event_type="integrity.flag", actor=self.other_student
            ).exists()
        )

    def test_blocked_second_attempt_is_flagged(self):
        self.start_and_submit()

        response = self.client.post(f"/api/exams/{self.exam.id}/start/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        entry = AuditLog.objects.get(event_type="integrity.flag")
        self.assertEqual(entry.actor, self.student)
        self.assertEqual(entry.metadata["reason"], "second_attempt_blocked")

    def test_normal_use_raises_no_integrity_flag(self):
        self.start_and_submit()

        self.assertFalse(AuditLog.objects.filter(event_type="integrity.flag").exists())

    def test_answer_content_is_never_logged(self):
        attempt_id = self.start_and_submit()
        from exam_delivery.models import Response as AnswerRow
        answer = AnswerRow.objects.get(attempt_id=attempt_id, question=self.question)
        self.client.force_authenticate(user=self.faculty)
        self.client.patch(
            f"/api/evaluation/responses/{answer.id}/",
            {"marks": "3", "feedback": "private feedback text"},
            format="json",
        )

        for entry in AuditLog.objects.all():
            blob = json.dumps(entry.metadata) + entry.description
            self.assertNotIn(SECRET_ANSWER, blob)
            self.assertNotIn("private feedback text", blob)


class RetentionTests(APITestCase):
    """TC-Audit-01: retention of at least one academic year, archive, retrieval."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="ret_admin", password="StrongPassword123!", role=User.Role.ADMIN
        )
        self.student = User.objects.create_user(
            username="ret_student", password="StrongPassword123!", role=User.Role.STUDENT
        )
        self.entries = {}
        for days in (10, 300, 399, 500, 800):
            entry = record_audit_event(f"aged.{days}", actor=self.student)
            backdate(entry, days)
            self.entries[days] = entry

    def run_archive(self, directory, *extra):
        out = StringIO()
        call_command("archive_audit_logs", "--archive-dir", directory, *extra, stdout=out)
        return out.getvalue()

    def test_retention_is_at_least_one_academic_year(self):
        self.assertGreaterEqual(retention_days(), MINIMUM_RETENTION_DAYS)

    @override_settings(AUDIT_LOG_RETENTION_DAYS=30)
    def test_retention_cannot_be_configured_below_a_year(self):
        self.assertEqual(retention_days(), MINIMUM_RETENTION_DAYS)

    @override_settings(AUDIT_LOG_RETENTION_DAYS=400)
    def test_archive_only_takes_entries_past_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_archive(directory)

            files = list(Path(directory).glob("audit-archive-*.jsonl"))
            self.assertEqual(len(files), 1)
            archived = [json.loads(line) for line in files[0].read_text().splitlines()]

        archived_types = {row["event_type"] for row in archived}
        self.assertEqual(archived_types, {"aged.500", "aged.800"})
        remaining = set(AuditLog.objects.values_list("event_type", flat=True))
        self.assertTrue({"aged.10", "aged.300", "aged.399"} <= remaining)
        self.assertFalse({"aged.500", "aged.800"} & remaining)

    @override_settings(AUDIT_LOG_RETENTION_DAYS=400)
    def test_archived_rows_keep_their_details(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_archive(directory)
            lines = next(Path(directory).glob("*.jsonl")).read_text().splitlines()

        row = next(r for r in map(json.loads, lines) if r["event_type"] == "aged.500")
        self.assertEqual(row["id"], self.entries[500].id)
        self.assertEqual(row["actor_id"], self.student.id)
        self.assertIn("created_at", row)

    @override_settings(AUDIT_LOG_RETENTION_DAYS=400)
    def test_archiving_is_itself_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_archive(directory)

        entry = AuditLog.objects.get(event_type="audit.archived")
        self.assertEqual(entry.metadata["entries"], 2)

    @override_settings(AUDIT_LOG_RETENTION_DAYS=400)
    def test_dry_run_changes_nothing(self):
        before = AuditLog.objects.count()
        with tempfile.TemporaryDirectory() as directory:
            output = self.run_archive(directory, "--dry-run")
            self.assertEqual(list(Path(directory).iterdir()), [])

        self.assertIn("2 entries are past it", output)
        self.assertEqual(AuditLog.objects.count(), before)

    @override_settings(AUDIT_LOG_RETENTION_DAYS=400)
    def test_nothing_is_archived_when_nothing_has_expired(self):
        AuditLog._base_manager.filter(
            event_type__in=["aged.500", "aged.800"]
        ).update(created_at=timezone.now() - timedelta(days=50))
        with tempfile.TemporaryDirectory() as directory:
            self.run_archive(directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_entries_inside_retention_cannot_be_purged(self):
        before = AuditLog.objects.count()

        with self.assertRaises(ValueError):
            AuditLog.objects.purge_expired(timezone.now() - timedelta(days=100))

        self.assertEqual(AuditLog.objects.count(), before)

    def test_retained_entries_can_be_retrieved_by_admin(self):
        self.client.force_authenticate(user=self.admin)
        since = (timezone.now() - timedelta(days=301)).isoformat()

        response = self.client.get(AUDIT_URL, {"since": since, "event_type": "aged.300"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["id"] for row in response.data], [self.entries[300].id])

    def test_entries_near_the_retention_limit_are_still_retrievable(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(AUDIT_URL, {"event_type": "aged.399"})

        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["actor"], self.student.id)

    def test_retrieval_can_filter_by_actor_and_date_range(self):
        self.client.force_authenticate(user=self.admin)
        until = (timezone.now() - timedelta(days=299)).date().isoformat()
        since = (timezone.now() - timedelta(days=401)).date().isoformat()

        response = self.client.get(
            AUDIT_URL, {"actor": self.student.id, "since": since, "until": until}
        )

        types = {row["event_type"] for row in response.data}
        self.assertEqual(types, {"aged.300", "aged.399"})

    def test_retrieval_limit_and_offset(self):
        self.client.force_authenticate(user=self.admin)

        first = self.client.get(AUDIT_URL, {"limit": 2})
        second = self.client.get(AUDIT_URL, {"limit": 2, "offset": 2})

        self.assertEqual(len(first.data), 2)
        self.assertEqual(len(second.data), 2)
        self.assertFalse(
            {row["id"] for row in first.data} & {row["id"] for row in second.data}
        )

    def test_bad_filters_are_rejected(self):
        self.client.force_authenticate(user=self.admin)

        for params in (
            {"since": "not-a-date"},
            {"actor": "abc"},
            {"limit": "0"},
            {"limit": "501"},
            {"offset": "-1"},
        ):
            with self.subTest(params=params):
                response = self.client.get(AUDIT_URL, params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_admins_can_retrieve_the_log(self):
        self.client.force_authenticate(user=self.student)

        response = self.client.get(AUDIT_URL)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
