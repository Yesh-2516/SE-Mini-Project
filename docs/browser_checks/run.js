// Browser checks for the student website (OEP-F-030, OEP-NF-005, TC-UX-01).
//
// Seeds a throwaway database, starts Django, and drives a real browser
// through the login, dashboard and exam pages. Runs axe-core on each screen
// and writes the results to results.md. See README.md in this folder.
"use strict";

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium } = require("playwright-core");

const HERE = __dirname;
const ROOT = path.resolve(HERE, "..", "..");
const PORT = process.env.PORT || "8765";
const BASE = "http://127.0.0.1:" + PORT;
const CHANNEL = process.env.BROWSER_CHANNEL || "msedge";
const AXE_PATH = require.resolve("axe-core/axe.min.js");
// ONLY=timeout runs just the checks whose names contain that text, and
// leaves results.md alone.
const ONLY = (process.env.ONLY || "").toLowerCase();
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"];

function findPython() {
  if (process.env.PYTHON) {
    return process.env.PYTHON;
  }
  const venv = process.platform === "win32"
    ? path.join(ROOT, ".venv", "Scripts", "python.exe")
    : path.join(ROOT, ".venv", "bin", "python");
  return fs.existsSync(venv) ? venv : "python";
}

const PYTHON = findPython();
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "oep-browser-checks-"));
const env = {
  ...process.env,
  BROWSER_CHECKS_DB: path.join(tempDir, "checks.sqlite3"),
  DJANGO_SETTINGS_MODULE: "check_settings",
  PYTHONPATH: [HERE, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
};

function manage(args) {
  const result = spawnSync(PYTHON, ["manage.py", ...args], { cwd: ROOT, env, encoding: "utf8" });
  if (result.status !== 0) {
    throw new Error("manage.py " + args.join(" ") + " failed:\n" + result.stderr);
  }
  return result.stdout;
}

// --- Reporting ---------------------------------------------------------------

const checks = [];
const scans = [];

function record(name, passed, detail) {
  checks.push({ name, passed, detail: detail || "" });
  console.log((passed ? "PASS " : "FAIL ") + name + (detail ? " (" + detail + ")" : ""));
}

async function check(name, body) {
  if (ONLY && !name.toLowerCase().includes(ONLY)) {
    return;
  }
  try {
    const detail = await body();
    record(name, true, detail);
  } catch (error) {
    record(name, false, String(error.message || error).split("\n")[0]);
  }
}

function expect(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function scan(page, screen) {
  await page.addScriptTag({ path: AXE_PATH });
  const result = await page.evaluate(async function (tags) {
    const run = await window.axe.run(document, { runOnly: { type: "tag", values: tags } });
    return {
      violations: run.violations.map(function (v) {
        return { id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length };
      }),
      passes: run.passes.length,
      incomplete: run.incomplete.map(function (v) { return v.id; }),
      incompleteNodes: run.incomplete.map(function (v) {
        return v.id + ": " + v.nodes.map(function (n) {
          return n.target.join(" ") + " [" + (n.any.concat(n.all)[0] || {}).message + "]";
        }).join("; ");
      }),
    };
  }, AXE_TAGS);
  scans.push({ screen, ...result });
  const summary = result.violations.map(function (v) { return v.id + " x" + v.nodes; }).join(", ");
  console.log("AXE  " + screen + ": " + (summary || "no violations"));
  result.incompleteNodes.forEach(function (line) { console.log("     review " + line); });
}

// --- Page helpers ------------------------------------------------------------

let seed;

async function newPage(browser, options) {
  const context = await browser.newContext(options);
  const page = await context.newPage();
  page.on("dialog", function (dialog) { dialog.accept(); });
  return page;
}

async function logIn(page, username, password) {
  await page.goto(BASE + "/login/");
  await page.getByLabel("Email, username or roll number").fill(username);
  await page.getByLabel("Password").fill(password || seed.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await page.waitForLoadState();
}

async function openExam(page, examId) {
  await page.goto(BASE + "/exams/" + examId + "/take/");
  await page.getByRole("button", { name: "Start exam" }).click();
  await page.locator("#exam-sitting").waitFor();
}

async function questionText(page) {
  return (await page.locator("#question-body legend, #question-body label.form-label").first().textContent()).trim();
}

// Answer whichever question is showing, whatever order the shuffle chose.
async function answerCurrent(page) {
  const text = await questionText(page);
  if (text.includes("capital of France")) {
    await page.getByLabel("Paris").check();
  } else if (text.includes("orbits the Sun")) {
    await page.getByLabel("True").check();
  } else if (text.includes("hydrogen")) {
    await page.locator("#answer-text").fill("oxygen");
  } else if (text.includes("sky is blue")) {
    await page.locator("#answer-text").fill("Rayleigh scattering");
  } else {
    await page.locator("#question-body input[type=radio]").first().check();
  }
  return text;
}

async function waitForSaved(page) {
  await page.waitForFunction(function () {
    return document.getElementById("save-status").textContent.startsWith("All answers saved");
  }, null, { timeout: 30000 });
}

async function goToQuestionType(page, wantText) {
  const count = await page.locator("#navigator button").count();
  for (let i = 0; i < count; i++) {
    await page.locator("#navigator button").nth(i).click();
    if (await page.locator("#answer-text").count() === (wantText ? 1 : 0)) {
      return;
    }
  }
  throw new Error("No " + (wantText ? "text" : "multiple-choice") + " question found");
}

// --- Checks ------------------------------------------------------------------

async function accessibilityScans(browser) {
  const page = await newPage(browser);
  await page.goto(BASE + "/login/");
  await scan(page, "Login");

  await page.getByLabel("Email, username or roll number").fill("student_axe");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await page.waitForLoadState();
  await scan(page, "Login with an error");

  await logIn(page, "student_axe");
  await scan(page, "Dashboard");

  await page.goto(BASE + "/exams/" + seed.sample + "/take/");
  await scan(page, "Exam intro");

  await page.getByRole("button", { name: "Start exam" }).click();
  await page.locator("#exam-sitting").waitFor();
  await goToQuestionType(page, false);
  await scan(page, "Exam, multiple-choice question");
  await goToQuestionType(page, true);
  await scan(page, "Exam, written-answer question");

  await page.getByRole("button", { name: "Submit exam" }).click();
  await page.locator("#exam-finished").waitFor();
  await scan(page, "Exam finished");
  await page.context().close();
}

async function fullSitting(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_sitting");
  const openLink = page.getByRole("link", { name: "Open Sample exam" });
  expect(await openLink.isVisible(), "Sample exam not listed with an Open button");
  expect(!(await page.getByText("Future exam").count()), "future exam is listed");
  await openLink.click();
  await page.getByRole("button", { name: "Start exam" }).click();
  await page.locator("#exam-sitting").waitFor();

  const total = await page.locator("#navigator button").count();
  expect(total === 4, "expected 4 questions, got " + total);
  for (let i = 0; i < total; i++) {
    await answerCurrent(page);
    if (i === 1) {
      await page.getByRole("button", { name: "Flag for review" }).click();
      await page.getByRole("button", { name: "Remove flag" }).waitFor();
    }
    if (i < total - 1) {
      await page.getByRole("button", { name: "Next" }).click();
    }
  }
  await waitForSaved(page);

  const progress = await page.locator("#progress").textContent();
  expect(progress.startsWith("4 of 4 answered, 1 flagged"), "progress says: " + progress);
  const labels = await page.locator("#navigator button").evaluateAll(function (buttons) {
    return buttons.map(function (b) { return b.getAttribute("aria-label"); });
  });
  expect(labels.every(function (l) { return l.includes("answered") && !l.includes("not answered"); }),
    "navigator labels: " + labels.join("; "));
  expect(labels.filter(function (l) { return l.endsWith(", flagged"); }).length === 1,
    "flag not shown in navigator");

  await page.getByRole("button", { name: "Submit exam" }).click();
  await page.getByRole("heading", { name: "Exam submitted" }).waitFor();
  const focused = await page.evaluate(function () { return document.activeElement.id; });
  expect(focused === "finished-heading", "focus is on " + focused);

  await page.getByRole("link", { name: "Back to dashboard" }).click();
  expect(await page.getByText("Submitted", { exact: true }).isVisible(), "dashboard doesn't show Submitted");

  await page.goto(BASE + "/exams/" + seed.sample + "/take/");
  await page.getByRole("button", { name: "Start exam" }).click();
  const error = page.locator("#exam-error");
  await error.waitFor();
  const message = await error.textContent();
  await page.context().close();
  return "4 answered, 1 flagged, submitted; second start says: " + message.trim();
}

async function keyboardOnly(browser) {
  const page = await newPage(browser);
  await page.goto(BASE + "/login/");
  await page.keyboard.press("Tab");
  const skip = await page.evaluate(function () { return document.activeElement.textContent.trim(); });
  expect(/skip/i.test(skip), "first Tab lands on: " + skip);

  await page.getByLabel("Email, username or roll number").focus();
  await page.keyboard.type("student_keyboard");
  await page.keyboard.press("Tab");
  await page.keyboard.type(seed.password);
  await page.keyboard.press("Enter");
  await page.waitForURL(/dashboard/);

  await page.goto(BASE + "/exams/" + seed.sample + "/take/");
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press("Tab");
    if (await page.evaluate(function () { return document.activeElement.id; }) === "start-button") {
      break;
    }
  }
  await page.keyboard.press("Enter");
  await page.locator("#exam-sitting").waitFor();

  await goToQuestionType(page, false);
  await page.locator("#question-body input[type=radio]").first().focus();
  await page.keyboard.press("ArrowDown");
  const checked = await page.locator("#question-body input:checked").count();
  expect(checked === 1, "arrow key didn't select an option");
  await waitForSaved(page);

  await page.locator("#next-button").focus();
  if (await page.locator("#next-button").isDisabled()) {
    await page.locator("#previous-button").focus();
  }
  await page.keyboard.press("Enter");
  const focused = await page.evaluate(function () { return document.activeElement.id; });
  expect(focused === "question-heading", "after moving question, focus is on " + focused);

  const outline = await page.locator("#next-button, #previous-button").first().evaluate(function (button) {
    button.focus();
    const style = getComputedStyle(button);
    return style.outlineStyle !== "none" || style.boxShadow !== "none";
  });
  expect(outline, "focused button has no visible focus indicator");
  await page.context().close();
  return "skip link first, radio chosen with arrow keys, focus moves to each new question";
}

async function reloadAndResume(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_resume");
  await openExam(page, seed.sample);
  await goToQuestionType(page, true);
  const text = await answerCurrent(page);
  const value = await page.locator("#answer-text").inputValue();
  await waitForSaved(page);

  await page.reload();
  await page.getByRole("button", { name: "Start exam" }).click();
  await page.locator("#exam-sitting").waitFor();
  const count = await page.locator("#navigator button").count();
  for (let i = 0; i < count; i++) {
    await page.locator("#navigator button").nth(i).click();
    if ((await questionText(page)) === text) {
      const restored = await page.locator("#answer-text").inputValue();
      expect(restored === value, "restored '" + restored + "', expected '" + value + "'");
      await page.context().close();
      return "answer to '" + text + "' restored after reload";
    }
  }
  throw new Error("question not found after reload");
}

// TC-Deliver-06: answers given while offline are saved on reconnecting, the
// timer is fetched again, and the answers are still there after a reload.
async function offlineAndReconnect(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_offline");
  await openExam(page, seed.sample);
  await goToQuestionType(page, true);

  await page.context().setOffline(true);
  const text = await answerCurrent(page);
  const value = await page.locator("#answer-text").inputValue();
  await page.waitForFunction(function () {
    return document.getElementById("save-status").textContent.startsWith("You're offline");
  }, null, { timeout: 10000 });

  const timerSynced = page.waitForRequest("**/timer/", { timeout: 10000 });
  await page.context().setOffline(false);
  await waitForSaved(page);
  await timerSynced;

  await page.reload();
  await page.getByRole("button", { name: "Start exam" }).click();
  await page.locator("#exam-sitting").waitFor();
  const count = await page.locator("#navigator button").count();
  for (let i = 0; i < count; i++) {
    await page.locator("#navigator button").nth(i).click();
    if ((await questionText(page)) === text) {
      const restored = await page.locator("#answer-text").inputValue();
      expect(restored === value, "restored '" + restored + "', expected '" + value + "'");
      await page.context().close();
      return "showed the offline message, saved and re-synced the timer on reconnecting, answer kept after reload";
    }
  }
  throw new Error("question not found after reload");
}

async function failedSaveRetries(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_retry");
  await openExam(page, seed.sample);
  let failures = 1;
  await page.route("**/autosave/", function (route) {
    if (failures-- > 0) {
      return route.abort("internetdisconnected");
    }
    return route.continue();
  });
  await answerCurrent(page);
  await page.waitForFunction(function () {
    return document.getElementById("save-status").textContent === "Not saved yet. Retrying...";
  }, null, { timeout: 10000 });
  await waitForSaved(page);
  await page.context().close();
  return "showed 'Not saved yet. Retrying...', then saved";
}

async function submitErrors(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_submit_error");
  await openExam(page, seed.sample);
  const error = page.locator("#exam-error");

  await page.route("**/submit/", function (route) {
    return route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Submissions are paused." }),
    });
  });
  await page.getByRole("button", { name: "Submit exam" }).click();
  await error.waitFor();
  const rejected = (await error.textContent()).trim();
  expect(rejected.includes("Submissions are paused.") && !rejected.includes("connection"),
    "server rejection says: " + rejected);

  await page.unroute("**/submit/");
  await page.route("**/submit/", function (route) { return route.abort("internetdisconnected"); });
  await page.getByRole("button", { name: "Submit exam" }).click();
  await page.waitForFunction(function () {
    return /Check your connection/.test(document.getElementById("exam-error").textContent);
  });
  await page.context().close();
  return "server rejection shows the server's reason; network failure asks to check the connection";
}

async function sessionLoss(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_session");
  await openExam(page, seed.sample);
  await page.context().clearCookies();
  await answerCurrent(page);
  const error = page.locator("#exam-error");
  await page.waitForFunction(function () {
    return /logged out/.test(document.getElementById("exam-error").textContent);
  }, null, { timeout: 15000 });
  const href = await error.getByRole("link", { name: "Log in" }).getAttribute("href");
  expect(href.includes("next=%2Fexams%2F" + seed.sample), "log in link: " + href);
  await page.context().close();
  return "logged-out message with a link back to the exam";
}

async function timeoutAutoSubmit(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_timeout");

  // Slow the timer down so overlapping requests at 0:00 would show up.
  let inFlight = 0;
  let maxInFlight = 0;
  await page.route("**/timer/", async function (route) {
    inFlight++;
    maxInFlight = Math.max(maxInFlight, inFlight);
    await new Promise(function (resolve) { setTimeout(resolve, 2500); });
    try {
      await route.continue();
    } finally {
      inFlight--;
    }
  });

  await openExam(page, seed.timed);
  await page.waitForFunction(function () {
    return document.getElementById("time-warning").textContent !== "";
  });
  const warning = await page.locator("#time-warning").textContent();
  expect(warning === "1 minute or less remaining.", "warning says: " + warning);
  await answerCurrent(page);
  await waitForSaved(page);

  await page.getByRole("heading", { name: "Time is up" }).waitFor({ timeout: 100000 });
  expect(maxInFlight <= 1, maxInFlight + " timer requests ran at once");
  await page.context().close();
  return "warning '" + warning + "', auto-submitted, at most " + maxInFlight + " timer request at a time";
}

async function scriptNotRun(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_xss");
  await openExam(page, seed.script);
  const text = await questionText(page);
  const injected = await page.evaluate(function () { return window.__injected; });
  expect(injected === undefined, "script in question text ran");
  expect(text.includes("<img"), "question text not shown as text: " + text);
  await page.context().close();
  return "markup shown as plain text";
}

async function narrowScreen(browser) {
  const page = await newPage(browser, { viewport: { width: 375, height: 740 } });
  const overflow = function () {
    return document.documentElement.scrollWidth > window.innerWidth;
  };
  await page.goto(BASE + "/login/");
  expect(!(await page.evaluate(overflow)), "login scrolls sideways");
  await logIn(page, "student_mobile");
  expect(!(await page.evaluate(overflow)), "dashboard scrolls sideways");
  await openExam(page, seed.sample);
  expect(!(await page.evaluate(overflow)), "exam page scrolls sideways");
  await page.context().close();
  return "login, dashboard and exam fit 375px";
}

async function futureExamHidden(browser) {
  const page = await newPage(browser);
  await logIn(page, "student_sitting");
  const response = await page.goto(BASE + "/exams/" + seed.future + "/take/");
  expect(response.status() === 404, "status " + response.status());
  await page.context().close();
  return "404";
}

// --- Main --------------------------------------------------------------------

function writeResults(browserVersion, axeVersion) {
  const commit = spawnSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT, encoding: "utf8" }).stdout.trim();
  const passed = checks.filter(function (c) { return c.passed; }).length;
  const violations = scans.reduce(function (n, s) { return n + s.violations.length; }, 0);
  const lines = [
    "# Browser check results",
    "",
    "Written by `run.js`. Don't edit by hand; run the checks again instead.",
    "",
    "| | |",
    "|---|---|",
    "| Date | " + new Date().toISOString().slice(0, 10) + " |",
    "| Commit | `" + commit + "` (uncommitted changes are included if there were any) |",
    "| Browser | " + CHANNEL + " " + browserVersion + ", headless |",
    "| axe-core | " + axeVersion + ", tags " + AXE_TAGS.join(", ") + " |",
    "| Result | " + passed + " of " + checks.length + " checks passed, " + violations + " axe violations |",
    "",
    "## Accessibility scans",
    "",
    "| Screen | Violations | Rules passed | Needs manual review |",
    "|---|---|---|---|",
  ];
  scans.forEach(function (s) {
    const found = s.violations.map(function (v) {
      return v.id + " (" + v.impact + ", " + v.nodes + ")";
    }).join(", ") || "None";
    lines.push("| " + s.screen + " | " + found + " | " + s.passes + " | " + (s.incomplete.join(", ") || "None") + " |");
  });
  lines.push("", "## Behaviour checks", "", "| Check | Result | Detail |", "|---|---|---|");
  checks.forEach(function (c) {
    lines.push("| " + c.name + " | " + (c.passed ? "Pass" : "**Fail**") + " | " + c.detail.replace(/\|/g, "\\|") + " |");
  });
  lines.push(
    "",
    "Automated scans find only part of WCAG 2.1 AA. Items under \"Needs manual review\" are ones axe",
    "could not decide, usually colour contrast over complex backgrounds. The usability test with a",
    "first-time user is separate: see `docs/usability_test.md`.",
    ""
  );
  fs.writeFileSync(path.join(HERE, "results.md"), lines.join("\n"));
}

(async function main() {
  console.log("Python: " + PYTHON);
  manage(["migrate", "-v", "0"]);
  const seedOutput = manage(["shell", "-c", "exec(open(r'" + path.join(HERE, "seed.py") + "').read())"]);
  seed = JSON.parse(seedOutput.split("\n").find(function (l) { return l.startsWith("SEED "); }).slice(5));

  const server = spawn(PYTHON, ["manage.py", "runserver", "--noreload", "127.0.0.1:" + PORT], {
    cwd: ROOT, env, stdio: "ignore",
  });
  let browser;
  try {
    for (let i = 0; ; i++) {
      try {
        await fetch(BASE + "/login/");
        break;
      } catch (error) {
        if (i > 60) {
          throw new Error("Django didn't start on " + BASE);
        }
        await new Promise(function (resolve) { setTimeout(resolve, 500); });
      }
    }

    browser = await chromium.launch({ channel: CHANNEL, headless: true });
    const axeVersion = require("axe-core/package.json").version;

    await check("Accessibility scans ran on every main screen", async function () {
      await accessibilityScans(browser);
      return scans.length + " screens";
    });
    await check("Full sitting: answer, flag, navigate and submit", function () { return fullSitting(browser); });
    await check("Keyboard only", function () { return keyboardOnly(browser); });
    await check("Reload and resume keeps saved answers", function () { return reloadAndResume(browser); });
    await check("Failed autosave retries", function () { return failedSaveRetries(browser); });
    await check("Offline, then reconnect", function () { return offlineAndReconnect(browser); });
    await check("Submit failure messages", function () { return submitErrors(browser); });
    await check("Session loss mid-exam", function () { return sessionLoss(browser); });
    await check("Script in question text doesn't run", function () { return scriptNotRun(browser); });
    await check("No sideways scrolling at 375px", function () { return narrowScreen(browser); });
    await check("Future exam page is hidden", function () { return futureExamHidden(browser); });
    await check("Timeout auto-submit (takes about a minute)", function () { return timeoutAutoSubmit(browser); });

    if (!ONLY) {
      writeResults(browser.version(), axeVersion);
    }
  } finally {
    if (browser) {
      await browser.close();
    }
    server.kill();
    fs.rmSync(tempDir, { recursive: true, force: true });
  }

  const failed = checks.filter(function (c) { return !c.passed; }).length;
  const violations = scans.reduce(function (n, s) { return n + s.violations.length; }, 0);
  console.log("\n" + (checks.length - failed) + "/" + checks.length + " checks passed, " + violations + " axe violations. See results.md.");
  process.exitCode = failed || violations ? 1 : 0;
})().catch(function (error) {
  console.error(error);
  process.exitCode = 1;
});
