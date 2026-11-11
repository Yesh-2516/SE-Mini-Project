# Browser check results

Written by `run.js`. Don't edit by hand; run the checks again instead.

| | |
|---|---|
| Date | 2026-11-11 |
| Commit | `a8dc541` (uncommitted changes are included if there were any) |
| Browser | msedge 157.0.4341.46, headless |
| axe-core | 4.10.3, tags wcag2a, wcag2aa, wcag21a, wcag21aa, best-practice |
| Result | 14 of 14 checks passed, 0 axe violations |

## Accessibility scans

| Screen | Violations | Rules passed | Needs manual review |
|---|---|---|---|
| Login | None | 33 | None |
| Login with an error | None | 37 | None |
| Dashboard | None | 30 | None |
| Exam intro | None | 30 | None |
| Exam, multiple-choice question | None | 39 | color-contrast |
| Exam, written-answer question | None | 39 | color-contrast |
| Exam, answered and flagged question | None | 39 | color-contrast |
| Exam finished | None | 31 | None |
| Admin dashboard | None | 28 | None |
| System health | None | 38 | None |

## Behaviour checks

| Check | Result | Detail |
|---|---|---|
| Accessibility scans ran on every main screen | Pass | 10 screens |
| Full sitting: answer, flag, navigate and submit | Pass | 4 answered, 1 flagged, submitted; second start says: A second attempt on the same exam is blocked. |
| Keyboard only | Pass | skip link first, radio chosen with arrow keys, focus moves to each new question |
| Question navigator and flags | Pass | jumped to question 3, marked current, answered and flagged (label 'Question 3, answered, flagged'), jump-to-flagged worked, submit warned '1 still flagged' |
| Admin health panel | Pass | admin sees 'Healthy. The server is running and the database is reachable.'; student gets 403 |
| Reload and resume keeps saved answers | Pass | answer to 'Explain why the sky is blue.' restored after reload |
| Failed autosave retries | Pass | showed 'Not saved yet. Retrying...', then saved |
| Offline, then reconnect | Pass | showed the offline message, saved and re-synced the timer on reconnecting, answer kept after reload |
| Submit failure messages | Pass | server rejection shows the server's reason; network failure asks to check the connection |
| Session loss mid-exam | Pass | logged-out message with a link back to the exam |
| Script in question text doesn't run | Pass | markup shown as plain text |
| No sideways scrolling at 375px | Pass | login, dashboard and exam fit 375px |
| Future exam page is hidden | Pass | 404 |
| Timeout auto-submit (takes about a minute) | Pass | warning '1 minute or less remaining.', auto-submitted, at most 1 timer request at a time |

Automated scans find only part of WCAG 2.1 AA. Items under "Needs manual review" are ones axe
could not decide, usually colour contrast over complex backgrounds. The usability test with a
first-time user is separate: see `docs/usability_test.md`.
