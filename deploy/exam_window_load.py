"""Simulate a class sitting an exam, for availability runs (OEP-NF-003).

Each student logs in through the API, starts the exam, then autosaves an
answer and syncs the timer at the same pace as the exam page in web/static.
Run it alongside deploy/uptime_probe.py so the uptime window has real exam
traffic, not an idle server.

    python deploy/exam_window_load.py http://127.0.0.1:8000 --exam 1 \
        --users student_a,student_b --password '...' --duration 1500

Uses only the standard library.
"""
import argparse
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request

TIMER_SYNC_SECONDS = 30  # Same as TIMER_SYNC_MS in web/static/web/exam.js.


class Counter:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = 0
        self.failures = {}

    def add(self, error=None):
        with self.lock:
            self.requests += 1
            if error:
                self.failures[error] = self.failures.get(error, 0) + 1


def call(base, method, path, counter, token=None, body=None):
    request = urllib.request.Request(
        base + path,
        method=method,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    if token:
        request.add_header("Authorization", "Token " + token)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            counter.add()
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        counter.add(f"{method} {path.split('/')[-2] or path} HTTP {exc.code}")
    except Exception as exc:
        counter.add(f"{method} {type(exc).__name__}")
    return None


def sit_exam(base, exam_id, username, password, deadline, save_every, counter):
    login = call(base, "POST", "/api/auth/login/", counter,
                 body={"username": username, "password": password})
    if not login:
        return
    token = login["token"]
    attempt = call(base, "POST", f"/api/exams/{exam_id}/start/", counter, token=token)
    if not attempt:
        return
    prefix = f"/api/exams/{exam_id}/attempts/{attempt['attempt_id']}/"
    questions = attempt["questions"]
    rng = random.Random(username)

    # Spread students out so they don't all save in the same second.
    time.sleep(rng.uniform(0, save_every))
    last_sync = time.monotonic()
    while time.monotonic() < deadline:
        question = rng.choice(questions)
        answer = rng.choice(question["options"]) if question["options"] else f"answer {rng.random():.4f}"
        call(base, "PUT", prefix + "autosave/", counter, token=token, body={
            "responses": [{"question_id": question["question_id"], "submitted_answer": answer}],
        })
        if time.monotonic() - last_sync >= TIMER_SYNC_SECONDS:
            call(base, "GET", prefix + "timer/", counter, token=token)
            last_sync = time.monotonic()
        time.sleep(save_every)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url", help="Site root, for example http://127.0.0.1:8000")
    parser.add_argument("--exam", type=int, required=True, help="Id of an open exam")
    parser.add_argument("--users", required=True, help="Comma-separated student usernames")
    parser.add_argument("--password", required=True, help="Password shared by those students")
    parser.add_argument("--duration", type=float, required=True, help="Seconds to keep the exam going")
    parser.add_argument("--save-every", type=float, default=10.0, help="Seconds between a student's saves (default 10)")
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    counter = Counter()
    deadline = time.monotonic() + args.duration
    threads = [
        threading.Thread(
            target=sit_exam,
            args=(base, args.exam, username.strip(), args.password, deadline, args.save_every, counter),
            daemon=True,
        )
        for username in args.users.split(",") if username.strip()
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    print(json.dumps({
        "students": len(threads),
        "requests": counter.requests,
        "failed": sum(counter.failures.values()),
        "failures": counter.failures,
    }, indent=2))
    return 0 if not counter.failures else 1


if __name__ == "__main__":
    sys.exit(main())
