# Browser Checks for the Student Website

Automated checks for the login, dashboard, exam and admin health pages (OEP-F-030, OEP-F-031, OEP-F-035, OEP-F-063, OEP-NF-005, TC-UX-01). They run in a real browser against a throwaway database, so `db.sqlite3` is never touched.

- **Accessibility:** axe-core scans 10 screens, including the admin dashboard and health panel, for WCAG 2.0 and 2.1 A and AA, plus best practices.
- **Behaviour:** a full sitting, keyboard-only use, the question navigator and flags, admin-only access to the health panel, reload and resume, autosave retry, going offline and reconnecting, submit errors, session loss, timeout auto-submit, script in question text, a 375px screen and a hidden future exam.

The latest results are in [results.md](results.md).

These checks aren't part of `pytest` or CI, because they need Node.js and a browser. Run them after changing anything in `web/`.

## Running

You need Node.js 18 or later, and Microsoft Edge or Google Chrome. From this folder:

```bash
npm install
npm run check
```

The script uses the project's `.venv` Python if it exists. The run takes about two minutes, most of it the one-minute exam timing out. It rewrites `results.md`, so commit that file with your change.

| Variable | Default | Purpose |
|---|---|---|
| `BROWSER_CHANNEL` | `msedge` | Set to `chrome` to use Google Chrome |
| `PYTHON` | `.venv` Python | The Python to run Django with |
| `PORT` | `8765` | Port for the test server |
| `ONLY` | Not set | Run only the checks whose names contain this text, for example `ONLY=timeout`. `results.md` isn't rewritten |

## Files

| File | Purpose |
|---|---|
| `run.js` | Seeds the database, starts Django, runs the checks and writes `results.md` |
| `seed.py` | Students and exams for the checks and for the usability test |
| `check_settings.py` | The normal settings, pointed at the throwaway database |
| `results.md` | Output of the last run |

The usability test with real first-time students is a separate, manual test: see [../usability_test.md](../usability_test.md).
