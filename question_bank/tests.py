import csv
import io
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from openpyxl import Workbook
from django.core.files.uploadedfile import SimpleUploadedFile
from question_bank.models import Question


class QuestionModelTests(TestCase):
    def test_create_mcq_question(self):
        question = Question.objects.create(
            text="Which language is used with Django?",
            question_type=Question.QuestionType.MCQ,
            options=["Python", "Java", "C++", "Ruby"],
            correct_answer="Python",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
        )

        self.assertEqual(question.question_type, "MCQ")
        self.assertEqual(len(question.options), 4)
        self.assertEqual(question.correct_answer, "Python")
        self.assertEqual(question.subject, "Computer Science")
        self.assertEqual(question.topic, "Django")
        self.assertEqual(question.difficulty, "EASY")

    def test_create_true_false_question(self):
        question = Question.objects.create(
            text="Django is a Python web framework.",
            question_type=Question.QuestionType.TRUE_FALSE,
            correct_answer="True",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
        )

        self.assertEqual(
            question.question_type,
            Question.QuestionType.TRUE_FALSE,
        )
        self.assertEqual(question.correct_answer, "True")

    def test_create_short_answer_question(self):
        question = Question.objects.create(
            text="What does ORM stand for?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Object-Relational Mapping",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.MEDIUM,
        )

        self.assertEqual(
            question.question_type,
            Question.QuestionType.SHORT_ANSWER,
        )
        self.assertEqual(
            question.correct_answer,
            "Object-Relational Mapping",
        )

    def test_question_string_representation(self):
        question = Question(
            text="What is Python?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A programming language",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.EASY,
        )

        self.assertEqual(
            str(question),
            "Short Answer: What is Python?",
        )


class QuestionAPITests(APITestCase):
    url = "/api/questions/"

    def setUp(self):
        self.staff_user = get_user_model().objects.create_user(
            username="question_staff",
            password="test-password-123",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.staff_user)

    def question_data(self, **overrides):
        data = {
            "text": "Which language is used with Django?",
            "question_type": "MCQ",
            "options": ["Python", "Java", "C++", "Ruby"],
            "correct_answer": "Python",
            "subject": "Computer Science",
            "topic": "Django",
            "difficulty": "EASY",
        }
        data.update(overrides)
        return data

    def test_create_valid_mcq(self):
        response = self.client.post(
            self.url,
            self.question_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(Question.objects.count(), 1)
        self.assertEqual(
            response.data["subject"],
            "Computer Science",
        )
        self.assertEqual(response.data["topic"], "Django")
        self.assertEqual(response.data["difficulty"], "EASY")

    def test_list_questions(self):
        Question.objects.create(
            text="Django uses Python.",
            question_type=Question.QuestionType.TRUE_FALSE,
            correct_answer="True",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
        )

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)

    def test_reject_mcq_with_too_few_options(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="Choose the language",
                options=["Python"],
                correct_answer="Python",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(Question.objects.count(), 0)

    def test_create_true_false_question(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="Django is a Python web framework.",
                question_type="TRUE_FALSE",
                options=[],
                correct_answer="True",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_create_short_answer_question(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="What does ORM stand for?",
                question_type="SHORT_ANSWER",
                options=[],
                correct_answer="Object-Relational Mapping",
                difficulty="MEDIUM",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_reject_mcq_answer_not_in_options(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="Choose the language",
                options=["Python", "Java"],
                correct_answer="C++",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_blank_question_text(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="   ",
                question_type="SHORT_ANSWER",
                options=[],
                correct_answer="Object-Relational Mapping",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_invalid_true_false_answer(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="Django is a Python web framework.",
                question_type="TRUE_FALSE",
                options=[],
                correct_answer="Maybe",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_duplicate_mcq_options(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="Choose the language",
                options=["Python", "python", "Java"],
                correct_answer="Python",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_invalid_question_type(self):
        response = self.client.post(
            self.url,
            self.question_data(
                text="What is Python?",
                question_type="ESSAY",
                options=[],
                correct_answer="A programming language",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_question_text(self):
        data = self.question_data()
        data.pop("text")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_question_type(self):
        data = self.question_data()
        data.pop("question_type")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_accept_mcq_answer_with_different_case_and_whitespace(self):
        response = self.client.post(
            self.url,
            self.question_data(correct_answer=" python "),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

    def test_reject_missing_subject(self):
        data = self.question_data()
        data.pop("subject")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_topic(self):
        data = self.question_data()
        data.pop("topic")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_missing_difficulty(self):
        data = self.question_data()
        data.pop("difficulty")

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_reject_invalid_difficulty(self):
        response = self.client.post(
            self.url,
            self.question_data(difficulty="VERY_EASY"),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_filter_questions_by_subject(self):
        Question.objects.create(
            text="What is Python?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A programming language",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.EASY,
        )
        Question.objects.create(
            text="What is a derivative?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A rate of change",
            subject="Mathematics",
            topic="Calculus",
            difficulty=Question.Difficulty.MEDIUM,
        )

        response = self.client.get(
            self.url,
            {"subject": "Mathematics"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["subject"],
            "Mathematics",
        )

    def test_filter_questions_by_topic(self):
        Question.objects.create(
            text="What is a variable?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A named storage location",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.EASY,
        )
        Question.objects.create(
            text="What is Django?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="A Python web framework",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.MEDIUM,
        )

        response = self.client.get(
            self.url,
            {"topic": "Python"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["topic"], "Python")

    def test_filter_questions_by_difficulty(self):
        Question.objects.create(
            text="Easy question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.EASY,
        )
        Question.objects.create(
            text="Hard question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Computer Science",
            topic="Python",
            difficulty=Question.Difficulty.HARD,
        )

        response = self.client.get(
            self.url,
            {"difficulty": "HARD"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["difficulty"],
            "HARD",
        )

    def test_filter_questions_by_multiple_tags(self):
        Question.objects.create(
            text="Easy Django question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
        )
        Question.objects.create(
            text="Hard Django question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.HARD,
        )
        Question.objects.create(
            text="Easy maths question",
            question_type=Question.QuestionType.SHORT_ANSWER,
            correct_answer="Answer",
            subject="Mathematics",
            topic="Algebra",
            difficulty=Question.Difficulty.EASY,
        )

        response = self.client.get(
            self.url,
            {
                "subject": "Computer Science",
                "topic": "Django",
                "difficulty": "HARD",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["difficulty"],
            "HARD",
        )

    def test_create_fill_in_the_blank_question(self):
        data = self.question_data()
        data.update({
            "text": "CPU stands for ____.",
            "question_type": "FILL_IN_THE_BLANK",
            "options": [],
            "correct_answer": "Central Processing Unit",
        })

        response = self.client.post(
            self.url,
            data,
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            response.data["question_type"],
            "FILL_IN_THE_BLANK",
        )

    def test_anonymous_user_cannot_access_question_bank(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_non_staff_user_cannot_access_question_bank(self):
        student = get_user_model().objects.create_user(
            username="question_student",
            password="test-password-123",
            is_staff=False,
        )
        self.client.force_authenticate(user=student)

        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )


class QuestionTemplateDownloadTests(APITestCase):
    def test_download_template_returns_csv_with_expected_headers(self):
        response = self.client.get("/api/questions/import/template/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Content-Type"],
            "text/csv; charset=utf-8",
        )
        self.assertIn(
            'attachment; filename="question_import_template.csv"',
            response["Content-Disposition"],
        )

        reader = csv.reader(io.StringIO(response.content.decode("utf-8")))
        rows = list(reader)

        self.assertEqual(
            rows[0],
            [
                "text",
                "question_type",
                "options",
                "correct_answer",
                "subject",
                "topic",
                "difficulty",
            ],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], "MCQ")

class QuestionBulkImportTests(APITestCase):
    url = "/api/questions/import/"

    headers = [
        "text",
        "question_type",
        "options",
        "correct_answer",
        "subject",
        "topic",
        "difficulty",
    ]

    def make_csv(self, rows, name="questions.csv"):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.headers)
        writer.writerows(rows)

        return SimpleUploadedFile(
            name,
            output.getvalue().encode("utf-8"),
            content_type="text/csv",
        )

    def valid_mcq_row(self):
        return [
            "Which language is used with Django?",
            "MCQ",
            '["Python","Java"]',
            "Python",
            "Computer Science",
            "Django",
            "EASY",
        ]

    def test_import_valid_csv(self):
        uploaded_file = self.make_csv([self.valid_mcq_row()])

        response = self.client.post(
            self.url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["imported_count"], 1)
        self.assertEqual(Question.objects.count(), 1)
        self.assertEqual(Question.objects.first().correct_answer, "Python")

    def test_reject_invalid_row_without_saving_any_questions(self):
        valid_row = self.valid_mcq_row()
        invalid_row = [
            "Choose a language",
            "MCQ",
            '["Python"]',
            "Python",
            "Computer Science",
            "Programming",
            "EASY",
        ]

        response = self.client.post(
            self.url,
            {"file": self.make_csv([valid_row, invalid_row])},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["imported_count"], 0)
        self.assertEqual(len(response.data["errors"]), 1)
        self.assertEqual(response.data["errors"][0]["row"], 3)
        self.assertEqual(Question.objects.count(), 0)

    def test_reject_upload_without_file(self):
        response = self.client.post(self.url, {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Question.objects.count(), 0)

    def test_reject_unsupported_file_type(self):
        uploaded_file = SimpleUploadedFile(
            "questions.txt",
            b"not a supported file",
            content_type="text/plain",
        )

        response = self.client.post(
            self.url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Unsupported file type", response.data["error"])
        self.assertEqual(Question.objects.count(), 0)

    def test_import_valid_excel(self):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(self.headers)
        worksheet.append(self.valid_mcq_row())

        output = io.BytesIO()
        workbook.save(output)
        workbook.close()

        uploaded_file = SimpleUploadedFile(
            "questions.xlsx",
            output.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

        response = self.client.post(
            self.url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["imported_count"], 1)
        self.assertEqual(Question.objects.count(), 1)

    def test_reject_missing_required_header(self):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.headers[:-1])
        writer.writerow(self.valid_mcq_row()[:-1])

        uploaded_file = SimpleUploadedFile(
            "questions.csv",
            output.getvalue().encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            self.url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Missing required columns", response.data["error"])
        self.assertEqual(Question.objects.count(), 0)

    def test_reject_duplicate_headers(self):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.headers + ["text"])
        writer.writerow(self.valid_mcq_row() + ["Duplicate value"])

        uploaded_file = SimpleUploadedFile(
            "questions.csv",
            output.getvalue().encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            self.url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("duplicate column headers", response.data["error"])
        self.assertEqual(Question.objects.count(), 0)

    def test_reject_malformed_options_json(self):
        row = self.valid_mcq_row()
        row[2] = '["Python",'

        response = self.client.post(
            self.url,
            {"file": self.make_csv([row])},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["imported_count"], 0)
        self.assertEqual(response.data["errors"][0]["row"], 2)
        self.assertIn("options", response.data["errors"][0]["errors"])
        self.assertEqual(Question.objects.count(), 0)

    def test_reject_csv_row_with_extra_columns(self):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.headers)
        writer.writerow(self.valid_mcq_row() + ["unexpected value"])

        uploaded_file = SimpleUploadedFile(
            "questions.csv",
            output.getvalue().encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            self.url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["imported_count"], 0)
        self.assertEqual(response.data["errors"][0]["row"], 2)
        self.assertEqual(Question.objects.count(), 0)

    def test_excel_error_reports_correct_row_after_blank_row(self):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(self.headers)
        worksheet.append(self.valid_mcq_row())
        worksheet.append([None] * len(self.headers))

        invalid_row = self.valid_mcq_row()
        invalid_row[2] = '["Python"]'
        worksheet.append(invalid_row)

        output = io.BytesIO()
        workbook.save(output)
        workbook.close()

        uploaded_file = SimpleUploadedFile(
            "questions.xlsx",
            output.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

        response = self.client.post(
            self.url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["imported_count"], 0)
        self.assertEqual(response.data["errors"][0]["row"], 4)
        self.assertEqual(Question.objects.count(), 0)
    def test_reject_file_larger_than_size_limit(self):
        from question_bank.views import MAX_IMPORT_FILE_SIZE

        uploaded_file = SimpleUploadedFile(
            "questions.csv",
            b"x" * (MAX_IMPORT_FILE_SIZE + 1),
            content_type="text/csv",
        )

        response = self.client.post(
            self.url,
            {"file": uploaded_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("5 MB", response.data["error"])
        self.assertEqual(Question.objects.count(), 0)


class QuestionDetailAPITests(APITestCase):
    def setUp(self):
        from exam_management.models import Exam, ExamQuestion

        self.Exam = Exam
        self.ExamQuestion = ExamQuestion

        self.question = Question.objects.create(
            text="What is Django?",
            question_type=Question.QuestionType.SHORT_ANSWER,
            options=[],
            correct_answer="A Python web framework",
            subject="Computer Science",
            topic="Django",
            difficulty=Question.Difficulty.EASY,
        )

    def detail_url(self, question_id=None):
        question_id = question_id or self.question.id
        return f"/api/questions/{question_id}/"

    def test_retrieve_question(self):
        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["text"], "What is Django?")

    def test_edit_question(self):
        response = self.client.patch(
            self.detail_url(),
            {"text": "What is Django REST Framework?"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.question.refresh_from_db()
        self.assertEqual(
            self.question.text,
            "What is Django REST Framework?",
        )

    def test_reject_invalid_question_edit(self):
        response = self.client.patch(
            self.detail_url(),
            {"text": "   "},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.question.refresh_from_db()
        self.assertEqual(self.question.text, "What is Django?")

    def test_delete_unattached_question(self):
        response = self.client.delete(self.detail_url())

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Question.objects.filter(pk=self.question.pk).exists()
        )

    def test_edit_question_attached_to_published_exam_is_blocked(self):
        exam = self.Exam.objects.create(title="Published Test")
        exam.status = "PUBLISHED"
        exam.save()
        self.ExamQuestion.objects.create(
            exam=exam,
            question=self.question,
            position=1,
        )

        response = self.client.patch(
            self.detail_url(),
            {"text": "Changed question"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("published or live exam", response.data["detail"])

    def test_delete_question_attached_to_published_exam_is_blocked(self):
        exam = self.Exam.objects.create(title="Published Test")
        exam.status = "PUBLISHED"
        exam.save()
        self.ExamQuestion.objects.create(
            exam=exam,
            question=self.question,
            position=1,
        )

        response = self.client.delete(self.detail_url())

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertTrue(
            Question.objects.filter(pk=self.question.pk).exists()
        )

    def test_delete_question_attached_to_draft_exam(self):
        exam = self.Exam.objects.create(title="Draft Test")
        self.ExamQuestion.objects.create(
            exam=exam,
            question=self.question,
            position=1,
        )

        response = self.client.delete(self.detail_url())

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Question.objects.filter(pk=self.question.pk).exists()
        )
        self.assertFalse(
            self.ExamQuestion.objects.filter(exam=exam).exists()
        )
    def test_edit_question_attached_to_draft_exam(self):
        exam = self.Exam.objects.create(title="Draft Test")
        self.ExamQuestion.objects.create(
            exam=exam,
            question=self.question,
            position=1,
        )

        response = self.client.patch(
            self.detail_url(),
            {"text": "Updated draft question"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.question.refresh_from_db()
        self.assertEqual(self.question.text, "Updated draft question")

    def test_edit_question_attached_to_live_exam_is_blocked(self):
        exam = self.Exam.objects.create(title="Live Test")
        exam.status = "LIVE"
        exam.save()
        self.ExamQuestion.objects.create(
            exam=exam,
            question=self.question,
            position=1,
        )

        response = self.client.patch(
            self.detail_url(),
            {"text": "Changed question"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("published or live exam", response.data["detail"])
