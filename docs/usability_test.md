# Usability Test with First-Time Students (OEP-NF-005, TC-UX-01)

OEP-NF-005 says a first-time student should be able to complete an exam without help, and that the interface should meet WCAG 2.1 AA where practical. The automated part (axe scans and keyboard, screen-size and error checks) is in `docs/browser_checks/`. This document covers the part that needs real people.

**Status:** Not run yet. Fill in the results table below after each session.

## Who to test with

- At least 3 people who have never seen the portal. Classmates outside the team are fine.
- Nobody who has worked on, reviewed or watched a demo of the website.
- If possible, one participant who mainly uses the keyboard, or a screen reader such as NVDA or Windows Narrator.

## Setting up

Use a throwaway database so the session doesn't touch `db.sqlite3`. From the project root, in PowerShell:

```powershell
.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "docs\browser_checks"
$env:DJANGO_SETTINGS_MODULE = "check_settings"
$env:BROWSER_CHECKS_DB = "$env:TEMP\oep-usability.sqlite3"
python manage.py migrate
python manage.py shell -c "exec(open('docs/browser_checks/seed.py').read())"
python manage.py runserver
```

This creates "Sample exam" with four questions (multiple choice, true/false, fill in the blank and a short answer), open for the next two hours. Give each participant their own account: `student_participant1`, `student_participant2` or `student_participant3`, all with the password `Str0ng-Passphrase!`. Run `seed.py` again on a new database file if you need more time or fresh accounts.

Open http://127.0.0.1:8000/ in a fresh browser window, on the login page.

## Running a session

Read this to the participant, then stay quiet:

> We're testing the website, not you. Please think out loud as you go. I can't answer questions or help during the task, but you can stop at any time. Here are your username and password. Please log in, take the exam called "Sample exam", answer every question, flag one question you'd want to check again, and submit.

While they work, note:

- Every time they hesitate for more than about 10 seconds, and what they were looking at
- Anything they say they expected to happen but didn't
- Any wrong click, such as pressing Submit too early or not finding Next
- Whether they ask for help. If you have to help, mark the task as failed, but let them finish

Afterwards, ask:

1. Was anything confusing?
2. Did you know how much time you had left, and whether your answers were saved?
3. Did you know what the flag did?
4. Out of 5, how easy was it? (1 = very hard, 5 = very easy)

## Pass criteria

The test passes when every participant finishes the task without help. If anyone needed help, or two or more people got stuck at the same point, raise an issue for that point, fix it, and test again with someone new.

## Results

| Date | Participant (no names) | Keyboard / screen reader? | Finished unaided? | Time taken | Ease (1–5) | Problems seen |
|---|---|---|---|---|---|---|
| | P1 | | | | | |
| | P2 | | | | | |
| | P3 | | | | | |

**Facilitator:**
**Issues raised:**

## Manual accessibility checks

axe can't check these, so do them once on the exam page:

| Check | How | Result |
|---|---|---|
| Zoom to 200% | Ctrl and + until 200%. Nothing is cut off and nothing overlaps | |
| Screen reader reads the question | With NVDA or Narrator, move to a new question. It reads the heading, then the question with its options | |
| Time warnings are announced | Use the one-minute exam in the seed data. The 1-minute warning is read out without moving focus | |
| Save status is announced | Change an answer. "All answers saved" is read out | |
| Focus is always visible | Tab through the whole exam page. You can always see where focus is | |
| Question navigator contrast | axe can't judge single-digit buttons, so this was worked out by hand: Bootstrap blue `#0d6efd` against white is 4.50:1 both ways, and the flag ring `#9a5b00` is 5.43:1 | Pass, just: AA needs 4.5:1. Don't lighten the blue |
