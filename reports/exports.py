"""PDF and Excel export of an exam report (OEP-F-052).

Both exporters are given the dictionary from ``reports.services`` that the
on-screen report uses, so an export always matches what is shown.

The PDF is written directly (plain text in a fixed-width font) so no extra
package is needed. Characters outside Latin-1 become "?" in the PDF; the
Excel file keeps them.
"""

import re
from io import BytesIO

from openpyxl import Workbook

XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
PDF_CONTENT_TYPE = "application/pdf"

# Page layout for the PDF (A4, 9pt Courier = 5.4pt per character).
_PAGE_WIDTH, _PAGE_HEIGHT = 595, 842
_LEFT_MARGIN, _TOP = 40, 800
_FONT_SIZE, _LEADING = 9, 11
_LINES_PER_PAGE = 60
_MAX_CHARS = 92


def summary_rows(report):
    summary = report["summary"]
    return [
        ("Exam", report["exam"]["title"]),
        ("Students counted", summary["students_counted"]),
        ("Average score", summary["average"]),
        ("Highest score", summary["highest"]),
        ("Lowest score", summary["lowest"]),
        ("Maximum possible score", summary["max_score"]),
        ("Pending evaluation", summary["pending_evaluation"]),
    ]


DISTRIBUTION_HEADER = ("Score range", "Students")
RESULTS_HEADER = ("Roll number", "Name", "Score", "Percentage")


def distribution_rows(report):
    return [(row["range"], row["students"]) for row in report["distribution"]]


def results_rows(report):
    return [
        (row["roll_number"], row["name"], row["score"], row["percentage"])
        for row in report["results"]
    ]


# ---------------------------------------------------------------- Excel

def render_xlsx(report):
    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "Summary"
    summary_sheet.append(("Measure", "Value"))
    for row in summary_rows(report):
        summary_sheet.append(row)

    distribution_sheet = workbook.create_sheet("Distribution")
    distribution_sheet.append(DISTRIBUTION_HEADER)
    for row in distribution_rows(report):
        distribution_sheet.append(row)

    results_sheet = workbook.create_sheet("Results")
    results_sheet.append(RESULTS_HEADER)
    for row in results_rows(report):
        results_sheet.append(row)

    # Text such as a name starting with "=" must stay text, never a formula.
    for sheet in workbook.worksheets:
        for sheet_row in sheet.iter_rows():
            for cell in sheet_row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ------------------------------------------------------------------ PDF

def _text(value):
    return "-" if value is None else str(value)


def report_lines(report):
    lines = [f"Class performance report - {report['exam']['title']}", ""]

    lines += ["Summary", "-------"]
    for label, value in summary_rows(report)[1:]:
        lines.append(f"{label:<28}{_text(value)}")

    lines += ["", "Score distribution", "------------------"]
    lines.append(f"{DISTRIBUTION_HEADER[0]:<16}{DISTRIBUTION_HEADER[1]:>8}")
    for label, count in distribution_rows(report):
        lines.append(f"{label:<16}{count:>8}")

    lines += ["", "Results", "-------"]
    lines.append(
        f"{RESULTS_HEADER[0]:<16}{RESULTS_HEADER[1]:<34}"
        f"{RESULTS_HEADER[2]:>8}{RESULTS_HEADER[3]:>12}"
    )
    for roll, name, score, percentage in results_rows(report):
        lines.append(f"{roll[:15]:<16}{name[:32]:<34}{_text(score):>8}{_text(percentage):>12}")
    if not report["results"]:
        lines.append("No graded results yet.")

    return [line[:_MAX_CHARS] for line in lines]


def _escape(text):
    text = re.sub(r"[\r\n\t]", " ", text)
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(page_lines):
    parts = [
        "BT",
        f"/F1 {_FONT_SIZE} Tf",
        f"{_LEADING} TL",
        f"{_LEFT_MARGIN} {_TOP} Td",
    ]
    for line in page_lines:
        parts.append(f"({_escape(line)}) Tj")
        parts.append("T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def lines_to_pdf(lines):
    """Lay text lines out on A4 pages and return the PDF file bytes."""

    pages = [
        lines[start:start + _LINES_PER_PAGE]
        for start in range(0, len(lines), _LINES_PER_PAGE)
    ] or [[]]

    # Objects: 1 catalog, 2 page tree, 3 font, then (page, content) pairs.
    kids = " ".join(f"{4 + 2 * index} 0 R" for index in range(len(pages)))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]
    for index, page_lines in enumerate(pages):
        content_number = 5 + 2 * index
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {_PAGE_WIDTH} {_PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_number} 0 R >>"
            ).encode()
        )
        stream = _page_stream(page_lines)
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode()
            + stream
            + b"\nendstream"
        )

    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_position = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()
    return bytes(output)


def render_pdf(report):
    return lines_to_pdf(report_lines(report))


EXPORTERS = {
    "pdf": (render_pdf, PDF_CONTENT_TYPE),
    "xlsx": (render_xlsx, XLSX_CONTENT_TYPE),
}
