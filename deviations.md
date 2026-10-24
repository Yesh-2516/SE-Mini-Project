# Sprint 1 — Deviations and Integration Notes

## 1. F-040: Automatic Objective Answer Grading

- Added `FILL_IN_THE_BLANK` as a supported question type.
- Blank or missing objective-answer submissions receive zero marks.
- Incorrect nonblank objective answers receive the configured negative marks.
- Answers are compared case-insensitively after whitespace normalization.
- Short-answer questions are excluded from automatic grading and require manual evaluation.

## 2. Temporary Authorization

- The question-bank API currently uses Django `IsAdminUser`, which checks `is_staff`.
- This is a temporary stand-in for the intended Faculty/Admin role-based authorization.
- Replace or integrate this check when the actual role implementation becomes available.
- Verify that future student-facing exam endpoints never expose correct answers.

## 3. Integration Dependencies

- The objective-grading function is implemented and tested independently.
- Integration with actual exam attempts, submitted responses, and the submission workflow remains pending the relevant teammate implementation.
- End-to-end grading has not yet been verified.

## 4. Follow-up

- Confirm these implementation choices against the SRS, SAD, and test plan.
- Update this document if review identifies additional deviations.
