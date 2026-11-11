"""Class performance reports and question-wise breakdowns.

OEP-F-051: average, highest, lowest and score distribution for an exam.
OEP-F-053: share of students who got each question right.
OEP-F-052 (exports) renders the exact dictionary built here, so what is
exported always matches what is shown on screen.

Which attempts count: for each student, their most recent attempt that is
submitted and fully graded. Attempts still waiting for evaluation are only
reported as ``pending_evaluation``.
"""

from decimal import Decimal, ROUND_HALF_UP

from exam_delivery.models import Attempt, Response

TWO_DECIMAL_PLACES = Decimal("0.01")
BUCKET_COUNT = 10  # 0-10%, 10-20%, ... 90-100%


def _two_places(value):
    return Decimal(value).quantize(TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)


def _student_name(student):
    return student.get_full_name() or student.username


def counted_attempts(exam):
    """Each student's latest submitted, fully graded attempt for the exam."""

    graded = (
        Attempt.objects
        .filter(exam=exam, status=Attempt.Status.SUBMITTED, is_graded=True)
        .select_related("student")
        .order_by("student_id", "-started_at", "-id")
    )
    latest = {}
    for attempt in graded:
        latest.setdefault(attempt.student_id, attempt)
    return list(latest.values())


def _bucket_labels():
    step = 100 // BUCKET_COUNT
    return [f"{i * step}-{(i + 1) * step}%" for i in range(BUCKET_COUNT)]


def _bucket_index(percentage):
    """Lower bound inclusive, upper bound exclusive; 100% joins the last bucket."""

    if percentage <= 0:
        return 0
    return min(int(percentage // (100 // BUCKET_COUNT)), BUCKET_COUNT - 1)


def build_exam_report(exam):
    """Summary, score distribution and per-student results for one exam."""

    exam_questions = list(exam.exam_questions.all())
    max_score = sum(eq.marks for eq in exam_questions)
    attempts = counted_attempts(exam)

    pending = (
        Attempt.objects
        .filter(exam=exam, status=Attempt.Status.SUBMITTED, is_graded=False)
        .values("student_id")
        .distinct()
        .count()
    )

    scores = [attempt.total_score for attempt in attempts]
    if scores:
        average = _two_places(sum(scores, Decimal("0")) / len(scores))
        highest = _two_places(max(scores))
        lowest = _two_places(min(scores))
    else:
        average = highest = lowest = None

    def percentage_of(score):
        if not max_score:
            return Decimal("0.00")
        return _two_places(Decimal(score) / Decimal(max_score) * 100)

    counts = [0] * BUCKET_COUNT
    results = []
    for attempt in attempts:
        percentage = percentage_of(attempt.total_score)
        counts[_bucket_index(percentage)] += 1
        results.append({
            "student_id": attempt.student_id,
            "roll_number": attempt.student.roll_number or "",
            "name": _student_name(attempt.student),
            "attempt_id": attempt.id,
            "score": _two_places(attempt.total_score),
            "percentage": percentage,
        })
    results.sort(key=lambda row: (-row["score"], row["roll_number"], row["name"]))

    return {
        "exam": {"id": exam.id, "title": exam.title},
        "summary": {
            "students_counted": len(attempts),
            "average": average,
            "highest": highest,
            "lowest": lowest,
            "max_score": max_score,
            "pending_evaluation": pending,
        },
        "distribution": [
            {"range": label, "students": count}
            for label, count in zip(_bucket_labels(), counts)
        ],
        "results": results,
    }


def build_question_breakdown(exam):
    """Per question: how many students got full marks (OEP-F-053).

    "Got it right" means full marks on the question, for every question
    type. ``average_marks`` shows partial credit on subjective answers.
    """

    attempts = counted_attempts(exam)
    attempt_ids = [attempt.id for attempt in attempts]
    students = len(attempts)

    responses_by_question = {}
    for response in Response.objects.filter(attempt_id__in=attempt_ids):
        responses_by_question.setdefault(response.question_id, []).append(response)

    questions = []
    for eq in exam.exam_questions.select_related("question").order_by("position"):
        rows = responses_by_question.get(eq.question_id, [])
        marks = [row.marks_obtained for row in rows if row.marks_obtained is not None]
        correct = sum(1 for value in marks if value >= eq.marks)
        answered = sum(1 for row in rows if row.submitted_answer.strip())
        questions.append({
            "position": eq.position,
            "question_id": eq.question_id,
            "text": eq.question.text,
            "question_type": eq.question.question_type,
            "max_marks": eq.marks,
            "students": students,
            "answered_count": answered,
            "correct_count": correct,
            "percent_correct": (
                _two_places(Decimal(correct) / students * 100) if students else None
            ),
            "average_marks": (
                _two_places(sum(marks, Decimal("0")) / students) if students else None
            ),
        })

    return {
        "exam": {"id": exam.id, "title": exam.title},
        "students_counted": students,
        "questions": questions,
    }
