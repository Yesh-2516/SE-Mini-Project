
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from exam_management.models import Exam, ExamQuestion
from exam_management.serializers import StudentExamQuestionSerializer
from question_bank.models import Question


class ExamNotOpen(PermissionDenied):
    default_detail = "This exam is not open."
    default_code = "exam_not_open"


def is_exam_open(exam, now=None):
    """Return True only while the exam's availability window is open."""

    if exam.availability_start is None or exam.availability_end is None:
        return False

    now = now or timezone.now()
    return exam.availability_start <= now < exam.availability_end


def get_student_exam_paper(*, exam, now=None):
    """Return an exam's questions as a student may see them (OEP-SR-004).

    Raises ExamNotOpen (403) outside the availability window. The result
    never contains correct answers. Callers still have to check that the
    student is allowed to sit this exam (publishing and course assignment).
    """

    if not is_exam_open(exam, now):
        raise ExamNotOpen()

    exam_questions = exam.exam_questions.select_related("question")

    return {
        "exam_id": exam.id,
        "title": exam.title,
        "duration_minutes": exam.duration_minutes,
        "availability_end": exam.availability_end,
        "questions": StudentExamQuestionSerializer(
            exam_questions,
            many=True,
        ).data,
    }


@transaction.atomic
def assemble_exam_manually(*, exam, question_ids):
    """Replace an exam's question list with manually selected questions."""

    if exam.status != Exam.Status.DRAFT:
        raise ValidationError("Only draft exams can be assembled.")

    if not isinstance(question_ids, list) or not question_ids:
        raise ValidationError(
            {"question_ids": "Provide a non-empty list of question IDs."}
        )

    if any(
        isinstance(question_id, bool) or not isinstance(question_id, int)
        for question_id in question_ids
    ):
        raise ValidationError(
            {"question_ids": "Every question ID must be an integer."}
        )

    if len(question_ids) != len(set(question_ids)):
        raise ValidationError(
            {"question_ids": "Duplicate question IDs are not allowed."}
        )

    questions = list(
        Question.objects.filter(id__in=question_ids)
    )
    questions_by_id = {question.id: question for question in questions}

    missing_ids = [
        question_id
        for question_id in question_ids
        if question_id not in questions_by_id
    ]
    if missing_ids:
        raise ValidationError({
            "question_ids": f"Unknown question IDs: {missing_ids}"
        })

    ExamQuestion.objects.filter(exam=exam).delete()

    ExamQuestion.objects.bulk_create([
        ExamQuestion(
            exam=exam,
            question=questions_by_id[question_id],
            position=position,
        )
        for position, question_id in enumerate(question_ids, start=1)
    ])

    return exam


@transaction.atomic
def generate_exam_by_rules(
    *,
    exam,
    subject,
    topic,
    difficulty_counts,
):
    """Replace a draft exam's questions using topic and difficulty counts."""

    if exam.status != Exam.Status.DRAFT:
        raise ValidationError("Only draft exams can be assembled.")

    if not isinstance(subject, str) or not subject.strip():
        raise ValidationError({"subject": "Subject cannot be blank."})

    if not isinstance(topic, str) or not topic.strip():
        raise ValidationError({"topic": "Topic cannot be blank."})

    if not isinstance(difficulty_counts, dict) or not difficulty_counts:
        raise ValidationError({
            "difficulty_counts": "Provide counts for at least one difficulty."
        })

    valid_difficulties = {
        Question.Difficulty.EASY,
        Question.Difficulty.MEDIUM,
        Question.Difficulty.HARD,
    }

    for difficulty, count in difficulty_counts.items():
        if difficulty not in valid_difficulties:
            raise ValidationError({
                "difficulty_counts": f"Invalid difficulty: {difficulty}"
            })

        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValidationError({
                "difficulty_counts": (
                    "Each difficulty count must be a non-negative integer."
                )
            })

    requested_total = sum(difficulty_counts.values())
    if requested_total == 0:
        raise ValidationError({
            "difficulty_counts": "At least one question must be requested."
        })

    selected_questions = []

    for difficulty, count in difficulty_counts.items():
        if count == 0:
            continue

        candidates = list(
            Question.objects.filter(
                subject__iexact=subject.strip(),
                topic__iexact=topic.strip(),
                difficulty=difficulty,
            ).order_by("?")[:count]
        )

        if len(candidates) < count:
            raise ValidationError({
                "difficulty_counts": (
                    f"Requested {count} {difficulty} questions for topic "
                    f"'{topic}', but only {len(candidates)} are available."
                )
            })

        selected_questions.extend(candidates)

    ExamQuestion.objects.filter(exam=exam).delete()

    ExamQuestion.objects.bulk_create([
        ExamQuestion(
            exam=exam,
            question=question,
            position=position,
        )
        for position, question in enumerate(selected_questions, start=1)
    ])

    return exam
