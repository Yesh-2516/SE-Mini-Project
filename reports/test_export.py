"""OEP-F-052 / TC-Result-03: export results and reports as PDF or Excel."""

from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook
from rest_framework import status
from rest_framework.test import APITestCase

from exam_management.models import Exam
from reports.exports import lines_to_pdf
from reports.testing import ReportsWorldMixin, make_user
from accounts.models import User


class ExportTests(ReportsWorldMixin, APITestCase):
    def setUp(self):
        self.create_world()
        self.report_url = f"/api/reports/exams/{self.exam.id}/"
        self.export_url = f"/api/reports/exams/{self.exam.id}/export/"
        self.client.force_authenticate(user=self.faculty)

    def export(self, export_format, **extra):
        return self.client.get(self.export_url, {"export_format": export_format}, **extra)

    def workbook(self):
        response = self.export("xlsx")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return load_workbook(BytesIO(response.content))

    # ---- Excel

    def test_results_can_be_exported_as_excel(self):
        response = self.export("xlsx")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(f"exam-{self.exam.id}-report.xlsx", response["Content-Disposition"])
        self.assertEqual(
            load_workbook(BytesIO(response.content)).sheetnames,
            ["Summary", "Distribution", "Results"],
        )

    def test_excel_summary_matches_the_screen(self):
        shown = self.client.get(self.report_url).data["summary"]

        sheet = self.workbook()["Summary"]
        exported = {row[0]: row[1] for row in sheet.iter_rows(min_row=2, values_only=True)}

        self.assertEqual(exported["Exam"], "Mixed Exam")
        self.assertEqual(exported["Students counted"], shown["students_counted"])
        self.assertAlmostEqual(float(exported["Average score"]), float(shown["average"]))
        self.assertAlmostEqual(float(exported["Highest score"]), float(shown["highest"]))
        self.assertAlmostEqual(float(exported["Lowest score"]), float(shown["lowest"]))
        self.assertEqual(exported["Maximum possible score"], shown["max_score"])

    def test_excel_distribution_matches_the_screen(self):
        shown = self.client.get(self.report_url).data["distribution"]

        sheet = self.workbook()["Distribution"]
        exported = [list(row) for row in sheet.iter_rows(min_row=2, values_only=True)]

        self.assertEqual(exported, [[row["range"], row["students"]] for row in shown])

    def test_excel_results_match_the_screen(self):
        shown = self.client.get(self.report_url).data["results"]

        sheet = self.workbook()["Results"]
        exported = list(sheet.iter_rows(min_row=2, values_only=True))

        self.assertEqual(len(exported), len(shown))
        for row, expected in zip(exported, shown):
            self.assertEqual(row[0], expected["roll_number"])
            self.assertEqual(row[1], expected["name"])
            self.assertAlmostEqual(float(row[2]), float(expected["score"]))
            self.assertAlmostEqual(float(row[3]), float(expected["percentage"]))

    def test_excel_never_turns_a_name_into_a_formula(self):
        evil = self.add_student("evil", "S666", "=HYPERLINK(\"http://x\")", "Tester")
        self.grade(evil, "1", "1", "1")

        sheet = self.workbook()["Results"]
        cells = [cell for row in sheet.iter_rows(min_row=2) for cell in row if cell.column == 2]
        evil_cell = next(c for c in cells if str(c.value).startswith("=HYPERLINK"))

        self.assertEqual(evil_cell.data_type, "s")

    # ---- PDF

    def test_results_can_be_exported_as_pdf(self):
        response = self.export("pdf")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f"exam-{self.exam.id}-report.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertTrue(response.content.rstrip().endswith(b"%%EOF"))

    def test_pdf_shows_the_same_figures_as_the_screen(self):
        shown = self.client.get(self.report_url).data

        pdf = self.export("pdf").content

        self.assertIn(b"Mixed Exam", pdf)
        for label, key in (("Average score", "average"), ("Highest score", "highest"),
                           ("Lowest score", "lowest")):
            self.assertIn(f"{label:<28}{shown['summary'][key]}".encode(), pdf)
        for row in shown["results"]:
            self.assertIn(row["roll_number"].encode(), pdf)
            self.assertIn(row["name"].encode(), pdf)

    def test_long_results_continue_on_further_pdf_pages(self):
        for index in range(80):
            student = make_user(f"bulk{index}", User.Role.STUDENT, roll_number=f"B{index:03}")
            self.grade(student, "1", "1", "1")

        pdf = self.export("pdf").content

        self.assertGreaterEqual(pdf.count(b"/Type /Page /"), 2)
        self.assertIn(b"B079", pdf)

    def test_pdf_handles_brackets_and_non_latin_text(self):
        report = {
            "exam": {"id": 1, "title": "Test (Final) \\ नमस्ते"},
            "summary": {"students_counted": 0, "average": None, "highest": None,
                        "lowest": None, "max_score": 10, "pending_evaluation": 0},
            "distribution": [],
            "results": [],
        }
        from reports.exports import render_pdf

        pdf = render_pdf(report)

        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertIn(rb"Test \(Final\) \\ ", pdf)

    def test_empty_pdf_is_still_a_valid_file(self):
        pdf = lines_to_pdf([])

        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))

    def test_exporting_an_empty_exam_works(self):
        empty = Exam.objects.create(title="Empty Exam", duration_minutes=30)

        for export_format in ("pdf", "xlsx"):
            with self.subTest(export_format=export_format):
                response = self.client.get(
                    f"/api/reports/exams/{empty.id}/export/", {"export_format": export_format}
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    # ---- format handling and access

    def test_export_format_is_required_and_checked(self):
        for params in ({}, {"export_format": "docx"}, {"export_format": ""}):
            with self.subTest(params=params):
                response = self.client.get(self.export_url, params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_export_format_is_case_insensitive(self):
        response = self.export("PDF")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_download_works_whatever_the_accept_header(self):
        response = self.export("pdf", HTTP_ACCEPT="application/pdf")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unknown_exam_returns_404(self):
        response = self.client.get(
            "/api/reports/exams/999999/export/", {"export_format": "pdf"}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_export(self):
        self.client.force_authenticate(user=self.admin)

        self.assertEqual(self.export("pdf").status_code, status.HTTP_200_OK)
        self.assertEqual(self.export("xlsx").status_code, status.HTTP_200_OK)

    def test_student_cannot_export(self):
        self.client.force_authenticate(user=self.s1)

        self.assertEqual(self.export("pdf").status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_export(self):
        self.client.force_authenticate(user=None)

        self.assertEqual(self.export("pdf").status_code, status.HTTP_401_UNAUTHORIZED)
