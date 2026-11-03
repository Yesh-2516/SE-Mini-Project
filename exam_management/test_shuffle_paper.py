from copy import deepcopy

from django.test import SimpleTestCase

from exam_management.services import shuffle_paper
from question_bank.models import Question
from question_bank.grading import grade_objective_answer


class ShufflePaperTests(SimpleTestCase):
    def setUp(self):
        self.questions = [
            {
                "question_id": 1,
                "position": 1,
                "marks": 2,
                "text": "Question one?",
                "question_type": Question.QuestionType.MCQ,
                "options": ["A", "B", "C", "D"],
            },
            {
                "question_id": 2,
                "position": 2,
                "marks": 1,
                "text": "Question two?",
                "question_type": Question.QuestionType.MCQ,
                "options": ["Red", "Green", "Blue"],
            },
            {
                "question_id": 3,
                "position": 3,
                "marks": 1,
                "text": "Is the sky blue?",
                "question_type": Question.QuestionType.TRUE_FALSE,
                "options": ["True", "False"],
            },
        ]

    def test_same_seed_produces_same_paper(self):
        first = shuffle_paper(self.questions, seed=12345)
        second = shuffle_paper(self.questions, seed=12345)

        self.assertEqual(first, second)

    def test_different_seeds_can_produce_different_question_orders(self):
        original_ids = [
            question["question_id"] for question in self.questions
        ]

        orders = {
            tuple(
                question["question_id"]
                for question in shuffle_paper(self.questions, seed=seed)
            )
            for seed in range(20)
        }

        self.assertGreater(len(orders), 1)
        self.assertEqual(
            sorted(original_ids),
            sorted(orders.pop()),
        )

    def test_question_ids_and_option_contents_are_preserved(self):
        shuffled = shuffle_paper(self.questions, seed=42)

        self.assertEqual(
            {question["question_id"] for question in shuffled},
            {question["question_id"] for question in self.questions},
        )

        original_options = {
            question["question_id"]: sorted(question["options"])
            for question in self.questions
        }

        for question in shuffled:
            self.assertEqual(
                sorted(question["options"]),
                original_options[question["question_id"]],
            )

    def test_positions_are_renumbered(self):
        shuffled = shuffle_paper(self.questions, seed=42)

        self.assertEqual(
            [question["position"] for question in shuffled],
            [1, 2, 3],
        )

    def test_true_false_options_remain_in_standard_order(self):
        shuffled = shuffle_paper(self.questions, seed=42)

        true_false = next(
            question
            for question in shuffled
            if question["question_type"] == Question.QuestionType.TRUE_FALSE
        )

        self.assertEqual(true_false["options"], ["True", "False"])

    def test_shuffle_does_not_mutate_original_paper(self):
        original = deepcopy(self.questions)

        shuffle_paper(self.questions, seed=42)

        self.assertEqual(self.questions, original)

    def test_empty_paper_returns_empty_list(self):
        self.assertEqual(shuffle_paper([], seed=42), [])

    def test_paper_contains_no_answer_fields(self):
        shuffled = shuffle_paper(self.questions, seed=42)

        for question in shuffled:
            self.assertNotIn("correct_answer", question)
            self.assertFalse(
                any("answer" in key.lower() for key in question)
            )

    def test_grading_remains_correct_after_shuffling(self):
        correct_answer = "B"

        shuffled = shuffle_paper(self.questions, seed=42)

        mcq = next(
            question
            for question in shuffled
            if question["question_id"] == 1
        )

        # Shuffling must preserve the answer text.
        self.assertIn(correct_answer, mcq["options"])

        score = grade_objective_answer(
            question_type="MCQ",
            correct_answer=correct_answer,
            submitted_answer=correct_answer,
            marks=2,
            negative_marks=0.5,
        )

        self.assertEqual(score, 2)

        wrong_score = grade_objective_answer(
            question_type="MCQ",
            correct_answer=correct_answer,
            submitted_answer="A",
            marks=2,
            negative_marks=0.5,
        )

        self.assertEqual(wrong_score, -0.5)
    
    def test_mcq_option_order_changes_for_different_seeds(self):
        option_orders = {
            tuple(question["options"])
            for seed in range(20)
            for question in shuffle_paper(self.questions, seed=seed)
            if question["question_id"] == 1
        }

        # Different seeds should produce different option orders.
        self.assertGreater(len(option_orders), 1)

        # Every generated order must preserve all original options.
        for order in option_orders:
            self.assertEqual(
                sorted(order),
                ["A", "B", "C", "D"],
            )

    def test_option_order_does_not_depend_on_question_order(self):
        first = shuffle_paper(self.questions, seed=10)
        second = shuffle_paper(
            list(reversed(self.questions)),
            seed=10,
        )

        first_options = {
            question["question_id"]: question["options"]
            for question in first
        }
        second_options = {
            question["question_id"]: question["options"]
            for question in second
        }

        self.assertEqual(first_options, second_options)