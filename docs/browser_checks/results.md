# Browser check results

Written by `run.js`. Don't edit by hand; run the checks again instead.

| | |
|---|---|
| Date | 2026-11-03 |
| Commit | `595a6dc` (uncommitted changes are included if there were any) |
| Browser | msedge 156.0.4314.58, headless |
| axe-core | 4.10.3, tags wcag2a, wcag2aa, wcag21a, wcag21aa, best-practice |
| Result | 11 of 11 checks passed, 0 axe violations |

## Accessibility scans

| Screen | Violations | Rules passed | Needs manual review |
|---|---|---|---|
| Login | None | 33 | None |
| Login with an error | None | 37 | None |
| Dashboard | None | 30 | None |
| Exam intro | None | 29 | None |
| Exam, multiple-choice question | None | 36 | color-contrast |
| Exam, written-answer question | None | 36 | color-contrast |
| Exam finished | None | 30 | None |

## Behaviour checks

| Check | Result | Detail |
|---|---|---|
| Accessibility scans ran on every main screen | Pass | 7 screens |
| Full sitting: answer, flag, navigate and submit | Pass | 4 answered, 1 flagged, submitted; second start says: A second attempt on the same exam is blocked. |
| Keyboard only | Pass | skip link first, radio chosen with arrow keys, focus moves to each new question |
| Reload and resume keeps saved answers | Pass | answer to 'Water is made of hydrogen and ____.' restored after reload |
| Failed autosave retries | Pass | showed 'Not saved yet. Retrying...', then saved |
| Submit failure messages | Pass | server rejection shows the server's reason; network failure asks to check the connection |
| Session loss mid-exam | Pass | logged-out message with a link back to the exam |
| Script in question text doesn't run | Pass | markup shown as plain text |
| No sideways scrolling at 375px | Pass | login, dashboard and exam fit 375px |
| Future exam page is hidden | Pass | 404 |
| Timeout auto-submit (takes about a minute) | Pass | warning '1 minute or less remaining.', auto-submitted, at most 1 timer request at a time |

Automated scans find only part of WCAG 2.1 AA. Items under "Needs manual review" are ones axe
could not decide, usually colour contrast over complex backgrounds. The usability test with a
first-time user is separate: see `docs/usability_test.md`.
