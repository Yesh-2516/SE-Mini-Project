
from decimal import Decimal

import pytest

from question_bank.grading import grade_objective_answer


@pytest.mark.parametrize(
    ("question_type", "correct_answer", "submitted_answer", "expected"),
    [
        ("MCQ", "Python", "Python", Decimal("4")),
        ("MCQ", "Python", "python", Decimal("4")),
        ("TRUE_FALSE", "True", " true ", Decimal("2")),
        (
            "FILL_IN_THE_BLANK",
            "Central Processing Unit",
            "central   processing unit",
            Decimal("3"),
        ),
        ("MCQ", "Python", "Java", Decimal("-1")),
        ("TRUE_FALSE", "False", "True", Decimal("-0.5")),
        ("MCQ", "Python", "", Decimal("0")),
        ("MCQ", "Python", None, Decimal("0")),
    ],
)
def test_grade_objective_answer(
    question_type, correct_answer, submitted_answer, expected
):
    score = grade_objective_answer(
        question_type=question_type,
        correct_answer=correct_answer,
        submitted_answer=submitted_answer,
        marks=(
            4 if question_type == "MCQ"
            else 2 if question_type == "TRUE_FALSE"
            else 3
        ),
        negative_marks=(
            1 if question_type == "MCQ"
            else Decimal("0.5") if question_type == "TRUE_FALSE"
            else 1
        ),
    )

    assert score == expected


def test_short_answer_cannot_be_graded_automatically():
    with pytest.raises(ValueError, match="cannot be graded automatically"):
        grade_objective_answer(
            question_type="SHORT_ANSWER",
            correct_answer="An explanation",
            submitted_answer="My explanation",
            marks=5,
            negative_marks=1,
        )


def test_negative_marks_cannot_be_negative():
    with pytest.raises(ValueError, match="cannot be negative"):
        grade_objective_answer(
            question_type="MCQ",
            correct_answer="A",
            submitted_answer="B",
            marks=4,
            negative_marks=-1,
        )

@pytest.mark.parametrize("invalid_marks", [-1, "NaN", "Infinity"])
def test_invalid_marks_are_rejected(invalid_marks):
    with pytest.raises(ValueError):
        grade_objective_answer(
            question_type="MCQ",
            correct_answer="A",
            submitted_answer="A",
            marks=invalid_marks,
            negative_marks=1,
        )


def test_invalid_negative_marks_are_rejected():
    with pytest.raises(ValueError):
        grade_objective_answer(
            question_type="MCQ",
            correct_answer="A",
            submitted_answer="B",
            marks=4,
            negative_marks="NaN",
        )

def test_incorrect_answer_with_zero_negative_marks_returns_zero():
    score = grade_objective_answer(
        question_type="MCQ",
        correct_answer="Python",
        submitted_answer="Java",
        marks=4,
        negative_marks=0,
    )

    assert score == Decimal("0")
