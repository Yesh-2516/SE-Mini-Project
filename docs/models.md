# Database Models Specification

Agreed database schema for the Online Exam Portal (Sprint 1 & Sprint 2).
Meeting notes compiled by: **Yashwantha R (CS614)**

---

## 1. User (`accounts.User`)

Extends Django's `AbstractUser` with institutional identification and role-based access control.

| Field | Type | Modifiers / Constraints | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Internal identifier |
| `username` | CharField(150) | Unique | Matches email or lowercased roll number |
| `email` | EmailField | Unique, lowercase | Institutional email address |
| `roll_number` | CharField(50) | Unique, uppercase, optional | Student registration / roll number |
| `role` | CharField(20) | Choices: `ADMIN`, `FACULTY`, `STUDENT` | Role for RBAC checks across the API |
| `password` | CharField(128) | Argon2 hash (OEP-SR-002) | Never stored in plaintext |
| `first_name` | CharField(150) | Optional | Given name |
| `last_name` | CharField(150) | Optional | Family name |
| `is_active` | BooleanField | Default: `True` | Soft-deletion / account deactivation flag (OEP-F-060) |
| `date_joined` | DateTimeField | Auto | Account registration timestamp |

---

## 2. Course (`courses.Course`)

Represents academic subjects/courses managed by administrators to organize faculty and students.

| Field | Type | Modifiers / Constraints | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Course identifier |
| `code` | CharField(30) | Unique, uppercase | Institutional course code (e.g., `CS614`) |
| `title` | CharField(200) | Required | Descriptive course name |
| `description` | TextField | Blank allowed | Course syllabus or notes |
| `faculty` | ManyToManyField(User) | Related: `courses_taught` | Mapped faculty instructors (role: `FACULTY`) |
| `students` | ManyToManyField(User) | Related: `courses_enrolled` | Enrolled students (role: `STUDENT`) |
| `created_at` | DateTimeField | Auto now add | Creation timestamp |
| `updated_at` | DateTimeField | Auto now | Last updated timestamp |

---

## 3. Question (`question_bank.Question`)

Reusable pool of assessment questions created and managed by Faculty/Admin.

| Field | Type | Modifiers / Constraints | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Question identifier |
| `text` | TextField | Required | The question prompt |
| `question_type` | CharField(20) | Choices: `MCQ`, `TRUE_FALSE`, `FILL_IN_THE_BLANK`, `SHORT_ANSWER` | Question classification |
| `options` | JSONField | Default: `list` | List of possible choices for MCQ and True/False |
| `correct_answer` | TextField | Required | The correct answer key (never served to students before or during exam) |
| `subject` | CharField(100) | Required | Subject tag (e.g., `Computer Science`) |
| `topic` | CharField(100) | Required | Topic tag (e.g., `Databases`) |
| `difficulty` | CharField(10) | Choices: `EASY`, `MEDIUM`, `HARD` | Difficulty rating for rule generation |
| `created_by` | ForeignKey(User) | Nullable, on_delete=SET_NULL | Faculty author |
| `created_at` | DateTimeField | Auto now add | Creation timestamp |
| `updated_at` | DateTimeField | Auto now | Last update timestamp |

---

## 4. Exam (`exam_management.Exam`)

Assessment definition configured and scheduled by Faculty or Admin.

| Field | Type | Modifiers / Constraints | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Exam identifier |
| `title` | CharField(200) | Required | Name of the exam (e.g., `Midterm 2026`) |
| `status` | CharField(20) | Choices: `DRAFT`, `PUBLISHED` | Lifecycle status |
| `duration_minutes`| PositiveIntegerField | Default: `60` | Permitted exam time once started |
| `availability_start`| DateTimeField | Optional | Window opening datetime (OEP-F-022) |
| `availability_end` | DateTimeField | Optional | Window closing datetime (OEP-F-022) |
| `negative_marking_enabled` | BooleanField | Default: `False` | Toggle for negative scoring scheme |
| `negative_marks` | DecimalField(6, 2) | Default: `0.00` | Penalty deducted for incorrect objective answers |
| `questions` | ManyToManyField(Question) | Through: `ExamQuestion` | Questions linked to this exam |
| `created_at` | DateTimeField | Auto now add | Creation timestamp |
| `updated_at` | DateTimeField | Auto now | Last updated timestamp |

---

## 5. ExamQuestion (`exam_management.ExamQuestion`)

Through-table mapping questions to an exam with explicit ordering and marks.

| Field | Type | Modifiers / Constraints | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Link identifier |
| `exam` | ForeignKey(Exam) | on_delete=CASCADE, related: `exam_questions` | Parent exam |
| `question` | ForeignKey(Question) | on_delete=PROTECT, related: `exam_question_links` | Linked question (protected from deletion when in exam) |
| `position` | PositiveIntegerField | Required | 1-based order in exam |
| `marks` | PositiveIntegerField | Default: `1` | Maximum marks awarded for this question |

**Constraints:**
- `UniqueConstraint(fields=["exam", "question"], name="unique_question_per_exam")`
- `UniqueConstraint(fields=["exam", "position"], name="unique_exam_question_position")`

---

## 6. Attempt (`exam_delivery.Attempt`)

Represents an individual student's timed sitting of a scheduled exam.

| Field | Type | Modifiers / Constraints | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Attempt identifier |
| `student` | ForeignKey(User) | on_delete=CASCADE, related: `exam_attempts` | The candidate taking the exam |
| `exam` | ForeignKey(Exam) | on_delete=CASCADE, related: `attempts` | The exam being attempted |
| `status` | CharField(20) | Choices: `IN_PROGRESS`, `SUBMITTED`, `EXPIRED` | Current sitting state |
| `started_at` | DateTimeField | Default: `timezone.now` | Server timestamp when sitting was initiated |
| `ends_at` | DateTimeField | Required | Authoritative deadline: `min(started_at + duration, availability_end)` |
| `submitted_at` | DateTimeField | Nullable, blank | Timestamp when submission completed |
| `submission_reason` | CharField(20) | Choices: `MANUAL`, `TIMEOUT`, Nullable | How the sitting concluded |
| `allow_reattempt` | BooleanField | Default: `False` | Permission flag granted by Admin/Faculty to retake (OEP-F-034) |
| `objective_score` | DecimalField(6, 2) | Default: `0.00` | Automated score calculated from objective answers (OEP-F-040) |
| `subjective_score` | DecimalField(6, 2) | Default: `0.00` | Manual score awarded by faculty for short answers (OEP-F-042) |
| `total_score` | DecimalField(6, 2) | Default: `0.00` | Final score (`objective_score + subjective_score`) (OEP-F-043) |
| `is_graded` | BooleanField | Default: `False` | True when all questions (including subjective) have been evaluated |
| `created_at` | DateTimeField | Auto now add | Record creation timestamp |
| `updated_at` | DateTimeField | Auto now | Record update timestamp |

**Methods:**
- `remaining_seconds(now=None)`: returns `max(0, int((ends_at - now).total_seconds()))` if `IN_PROGRESS`, else `0`.
- `is_expired(now=None)`: returns `now >= ends_at`.

---

## 7. Response (`exam_delivery.Response`)

Stores the student's answer, flag state, and evaluation results for one question in an attempt.

| Field | Type | Modifiers / Constraints | Description |
|---|---|---|---|
| `id` | BigAutoField | Primary Key | Response identifier |
| `attempt` | ForeignKey(Attempt) | on_delete=CASCADE, related: `responses` | Parent sitting attempt |
| `question` | ForeignKey(Question) | on_delete=PROTECT, related: `exam_responses` | Associated question |
| `submitted_answer` | TextField | Blank allowed | Student's answer string |
| `is_flagged` | BooleanField | Default: `False` | Bookmark flag for student review (OEP-F-031) |
| `marks_obtained` | DecimalField(6, 2) | Nullable | Score awarded for this specific response |
| `feedback` | TextField | Blank allowed | Faculty remarks for subjective responses (OEP-F-042) |
| `evaluated_at` | DateTimeField | Nullable | When evaluation was performed |
| `evaluated_by` | ForeignKey(User) | Nullable, on_delete=SET_NULL | Faculty member who evaluated (for manual grading) |
| `created_at` | DateTimeField | Auto now add | Initial answer timestamp |
| `updated_at` | DateTimeField | Auto now | Auto-save / modification timestamp |

**Constraints:**
- `UniqueConstraint(fields=["attempt", "question"], name="unique_attempt_question")`
