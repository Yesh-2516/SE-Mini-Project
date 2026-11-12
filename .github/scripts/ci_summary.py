"""Write test and coverage results to the GitHub Actions run summary.

Usage:
  python ci_summary.py tests <label> <junit.xml> <coverage.json>
  python ci_summary.py pipeline <coverage.json> <junit.xml>...

``tests`` describes one test job. ``pipeline`` combines every test job and
adds the result of each job in the pipeline, read from the NEEDS environment
variable (``toJSON(needs)`` in the workflow).
"""

import json
import os
import sys
import xml.etree.ElementTree as ET

JOB_NAMES = {
    "build": "Build and Setup",
    "backend-tests": "Backend Testing",
    "frontend-tests": "Frontend Testing",
    "backend-lint": "Backend Linting (Ruff)",
    "frontend-lint": "Frontend Linting (ESLint)",
    "backend-security": "Backend Security Scan (Bandit)",
    "dependency-audit": "Dependency Audit (pip-audit)",
    "codeql": "CodeQL Security Analysis",
}
ICONS = {"success": "✅", "failure": "❌", "cancelled": "⚪", "skipped": "⏭️"}


def count_tests(paths):
    """Count tests the way pytest's final line does.

    Rows are grouped by (classname, name) in case a test is written more than
    once. A test failed if any of its rows failed, and was skipped if every
    row was skipped.
    """

    outcomes = {}
    for path in paths:
        if not os.path.exists(path):
            continue
        for case in ET.parse(path).getroot().iter("testcase"):
            key = (path, case.get("classname"), case.get("name"))
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            previous = outcomes.get(key)
            if previous == "failed" or outcome == "failed":
                outcomes[key] = "failed"
            elif previous == "passed" or outcome == "passed":
                outcomes[key] = "passed"
            else:
                outcomes[key] = "skipped"

    values = list(outcomes.values())
    return {
        "tests": len(values),
        "passed": values.count("passed"),
        "failed": values.count("failed"),
        "skipped": values.count("skipped"),
    }


def read_coverage(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["totals"]["percent_covered"], data["files"]


def bar(percent, width=20):
    filled = round(percent / 100 * width)
    return "█" * filled + "░" * (width - filled)


def coverage_lines(coverage):
    if coverage is None:
        return ["Coverage: not available"]
    percent, files = coverage
    lines = [
        f"### Test coverage: **{percent:.2f}%**",
        "",
        f"`{bar(percent)}` {percent:.2f}%",
        "",
        "<details><summary>Coverage by module</summary>",
        "",
        "| Module | Coverage |",
        "|---|---:|",
    ]
    modules = {}
    for name, info in files.items():
        module = name.replace("\\", "/").split("/")[0]
        summary = info["summary"]
        covered, total = modules.get(module, (0, 0))
        modules[module] = (
            covered + summary["covered_lines"] + summary.get("covered_branches", 0),
            total + summary["num_statements"] + summary.get("num_branches", 0),
        )
    for module, (covered, total) in sorted(modules.items()):
        pct = 100 * covered / total if total else 100
        lines.append(f"| `{module}` | {pct:.1f}% |")
    lines += ["", "</details>"]
    return lines


def test_lines(totals):
    rate = 100 * totals["passed"] / (totals["tests"] - totals["skipped"] or 1)
    return [
        "| Tests | ✅ Passed | ❌ Failed | ⏭️ Skipped | Pass rate |",
        "|---:|---:|---:|---:|---:|",
        f"| {totals['tests']} | {totals['passed']} | {totals['failed']} "
        f"| {totals['skipped']} | **{rate:.1f}%** |",
    ]


def write(lines, outputs):
    text = "\n".join(lines) + "\n"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            for key, value in outputs.items():
                fh.write(f"{key}={value}\n")


def tests_mode(label, junit, coverage_json):
    totals = count_tests([junit])
    coverage = read_coverage(coverage_json)
    lines = [f"## 🧪 {label}", ""] + test_lines(totals) + [""] + coverage_lines(coverage)
    write(lines, {
        "passed": totals["passed"],
        "coverage": f"{coverage[0]:.2f}" if coverage else "n/a",
    })


def pipeline_mode(coverage_json, junits):
    totals = count_tests(junits)
    coverage = read_coverage(coverage_json)
    needs = json.loads(os.environ.get("NEEDS", "{}"))

    headline = (
        f"**{totals['passed']} passed**, {totals['failed']} failed, "
        f"{totals['skipped']} skipped"
    )
    if coverage:
        headline += f" · **{coverage[0]:.2f}% coverage**"

    lines = [
        "# 📊 Pipeline Summary",
        "",
        headline,
        "",
        "## Jobs",
        "",
        "| Job | Result |",
        "|---|---|",
    ]
    for job_id, name in JOB_NAMES.items():
        result = needs.get(job_id, {}).get("result", "not run")
        lines.append(f"| {name} | {ICONS.get(result, '•')} {result} |")
    lines += ["", "## All tests", ""] + test_lines(totals) + [""] + coverage_lines(coverage)
    write(lines, {"coverage": f"{coverage[0]:.2f}" if coverage else "n/a"})


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "tests":
        tests_mode(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == "pipeline":
        pipeline_mode(sys.argv[2], sys.argv[3:])
    else:
        sys.exit(f"Unknown mode: {mode}")
