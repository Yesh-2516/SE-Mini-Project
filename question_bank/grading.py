
from decimal import Decimal, InvalidOperation


OBJECTIVE_QUESTION_TYPES = {"MCQ", "TRUE_FALSE", "FILL_IN_THE_BLANK"}


def grade_objective_answer(
    question_type,
    correct_answer,
    submitted_answer,
    marks,
    negative_marks=0,
):
    """Return the score for one objectively graded answer."""

    if question_type not in OBJECTIVE_QUESTION_TYPES:
        raise ValueError("This question type cannot be graded automatically.")

    try:
        marks = Decimal(str(marks))
        negative_marks = Decimal(str(negative_marks))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Marks must be valid numbers.") from None

    if not marks.is_finite() or not negative_marks.is_finite():
        raise ValueError("Marks must be finite numbers.")

    if marks < 0 or negative_marks < 0:
        raise ValueError("Marks cannot be negative.")

    if submitted_answer is None:
        return Decimal("0")

    if not isinstance(submitted_answer, str):
        raise ValueError("Submitted answer must be a string.")

    if not isinstance(correct_answer, str) or not correct_answer.strip():
        raise ValueError("Correct answer must be a non-empty string.")

    if not submitted_answer.strip():
        return Decimal("0")

    correct = " ".join(correct_answer.split()).casefold()
    submitted = " ".join(submitted_answer.split()).casefold()

    if submitted == correct:
        return marks

    return -negative_marks
