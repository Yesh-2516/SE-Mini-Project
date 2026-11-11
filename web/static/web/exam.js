// Student exam screen. The server owns the deadline, the answers and the
// submission; this page only displays them and sends changes back.
(function () {
  "use strict";

  // Answers save 2 seconds after the last change, and every 30 seconds
  // anything still unsaved is sent again, so a missed save is never stuck
  // waiting for the next change (OEP-F-035).
  const SAVE_DELAY_MS = 2000;
  const SAVE_INTERVAL_MS = 30000;
  const SAVE_RETRY_MS = 15000;
  const TIMER_SYNC_MS = 30000; // Also keeps the session from going idle.
  const WARNING_SECONDS = [300, 60];
  const FINAL_SAVE_SECONDS = 5; // Don't wait for the delay this close to the end.

  const app = document.getElementById("exam-app");
  const examId = app.dataset.examId;
  const elements = {};
  [
    "exam-error", "exam-intro", "exam-sitting", "exam-finished", "start-button",
    "timer", "save-status", "time-warning", "question-heading", "question-marks",
    "question-body", "previous-button", "next-button", "flag-button", "navigator",
    "progress", "submit-button", "finished-heading", "finished-message",
  ].forEach(function (id) {
    elements[id] = document.getElementById(id);
  });

  const state = {
    attemptId: null,
    questions: [],
    index: 0,
    unsaved: new Map(), // question_id -> answer waiting to be saved
    deadline: 0, // Browser time at which the server's remaining time runs out.
    warned: new Set(),
    finished: false,
    saving: false,
    syncing: false,
    saveTimer: null,
    tickTimer: null,
    syncTimer: null,
    intervalSaveTimer: null,
  };

  class ApiError extends Error {
    constructor(status, detail) {
      super(detail);
      this.status = status;
    }
  }

  async function api(method, path, body) {
    const response = await fetch(path, {
      method: method,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": app.dataset.csrfToken,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(function () {
      return {};
    });
    if (!response.ok) {
      throw new ApiError(response.status, data.detail || "Something went wrong.");
    }
    return data;
  }

  function attemptPath(suffix) {
    return "/api/exams/" + examId + "/attempts/" + state.attemptId + "/" + suffix;
  }

  function showError(message) {
    elements["exam-error"].textContent = message;
    elements["exam-error"].hidden = false;
  }

  function clearError() {
    elements["exam-error"].hidden = true;
  }

  function handleSessionLoss(error) {
    if (error.status === 401) {
      state.finished = true;
      stopTimers();
      showError("You have been logged out. Log in again to continue; your saved answers are safe.");
      const link = document.createElement("a");
      link.href = app.dataset.loginUrl + "?next=" + encodeURIComponent(location.pathname);
      link.className = "alert-link ms-1";
      link.textContent = "Log in";
      elements["exam-error"].append(link);
      return true;
    }
    return false;
  }

  function stopTimers() {
    clearInterval(state.tickTimer);
    clearInterval(state.syncTimer);
    clearInterval(state.intervalSaveTimer);
    clearTimeout(state.saveTimer);
  }

  async function startExam() {
    clearError();
    elements["start-button"].disabled = true;
    try {
      const data = await api("POST", "/api/exams/" + examId + "/start/");
      state.attemptId = data.attempt_id;
      state.questions = data.questions;
      setRemaining(data.remaining_seconds);
      elements["exam-intro"].hidden = true;
      elements["exam-sitting"].hidden = false;
      showQuestion(0, false);
      state.tickTimer = setInterval(tick, 1000);
      state.syncTimer = setInterval(syncTimer, TIMER_SYNC_MS);
      state.intervalSaveTimer = setInterval(save, SAVE_INTERVAL_MS);
      tick();
    } catch (error) {
      elements["start-button"].disabled = false;
      if (!handleSessionLoss(error)) {
        showError(error.message);
      }
    }
  }

  function setRemaining(seconds) {
    state.deadline = Date.now() + seconds * 1000;
  }

  function remainingSeconds() {
    return Math.max(0, Math.ceil((state.deadline - Date.now()) / 1000));
  }

  function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = String(seconds % 60).padStart(2, "0");
    const paddedMinutes = String(minutes).padStart(2, "0");
    return hours ? hours + ":" + paddedMinutes + ":" + secs : paddedMinutes + ":" + secs;
  }

  function tick() {
    if (state.finished) {
      return;
    }
    const seconds = remainingSeconds();
    elements.timer.textContent = formatTime(seconds);

    WARNING_SECONDS.forEach(function (limit) {
      if (seconds <= limit && !state.warned.has(limit)) {
        state.warned.add(limit);
        if (seconds > 0) {
          const minutes = Math.ceil(limit / 60);
          elements["time-warning"].textContent =
            minutes + (minutes === 1 ? " minute" : " minutes") + " or less remaining.";
        }
      }
    });

    if (seconds <= FINAL_SAVE_SECONDS) {
      save();
    }
    if (seconds === 0) {
      syncTimer();
    }
  }

  async function syncTimer() {
    // At 0:00 tick() calls this every second; only one request at a time.
    if (state.finished || state.attemptId === null || state.syncing) {
      return;
    }
    state.syncing = true;
    try {
      // Reading the timer after the deadline makes the server auto-submit.
      const data = await api("GET", attemptPath("timer/"));
      if (data.status !== "IN_PROGRESS") {
        finish("Time is up", "Your exam was submitted automatically with the answers saved before the deadline.");
        return;
      }
      setRemaining(data.remaining_seconds);
    } catch (error) {
      handleSessionLoss(error);
    } finally {
      state.syncing = false;
    }
  }

  function currentQuestion() {
    return state.questions[state.index];
  }

  function showQuestion(index, moveFocus) {
    state.index = index;
    const question = currentQuestion();
    elements["question-heading"].textContent =
      "Question " + question.position + " of " + state.questions.length;
    elements["question-marks"].textContent =
      question.marks + (question.marks === 1 ? " mark" : " marks");

    elements["question-body"].replaceChildren(buildAnswerControl(question));

    elements["previous-button"].disabled = index === 0;
    elements["next-button"].disabled = index === state.questions.length - 1;
    elements["flag-button"].setAttribute("aria-pressed", String(question.is_flagged));
    elements["flag-button"].textContent = question.is_flagged ? "Remove flag" : "Flag for review";
    renderNavigator();

    if (moveFocus) {
      elements["question-heading"].focus();
    }
  }

  function buildAnswerControl(question) {
    if (question.options.length) {
      return buildOptions(question);
    }

    const wrapper = document.createElement("div");
    const label = document.createElement("label");
    label.className = "form-label";
    label.htmlFor = "answer-text";
    label.textContent = question.text;

    const short = question.question_type === "FILL_IN_THE_BLANK";
    const input = document.createElement(short ? "input" : "textarea");
    input.id = "answer-text";
    input.className = "form-control";
    if (short) {
      input.type = "text";
    } else {
      input.rows = 6;
    }
    input.value = question.submitted_answer;
    input.addEventListener("input", function () {
      changeAnswer(question, input.value);
    });

    wrapper.append(label, input);
    return wrapper;
  }

  function buildOptions(question) {
    const fieldset = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.className = "fs-6";
    legend.textContent = question.text;
    fieldset.append(legend);

    question.options.forEach(function (option, optionIndex) {
      const row = document.createElement("div");
      row.className = "form-check mb-2";

      const input = document.createElement("input");
      input.className = "form-check-input";
      input.type = "radio";
      input.name = "answer";
      input.id = "option-" + optionIndex;
      input.value = option;
      input.checked = question.submitted_answer === option;
      input.addEventListener("change", function () {
        changeAnswer(question, option);
      });

      const label = document.createElement("label");
      label.className = "form-check-label";
      label.htmlFor = input.id;
      label.textContent = option;

      row.append(input, label);
      fieldset.append(row);
    });
    return fieldset;
  }

  function isAnswered(question) {
    return question.submitted_answer.trim() !== "";
  }

  function renderNavigator() {
    const buttons = state.questions.map(function (question, index) {
      const button = document.createElement("button");
      const answered = isAnswered(question);
      button.type = "button";
      button.className = "btn nav-question " + (answered ? "btn-primary" : "btn-outline-primary");
      if (question.is_flagged) {
        button.classList.add("is-flagged");
      }
      button.textContent = question.position + (question.is_flagged ? "*" : "");
      button.setAttribute(
        "aria-label",
        "Question " + question.position + ", " +
          (answered ? "answered" : "not answered") +
          (question.is_flagged ? ", flagged" : "")
      );
      if (index === state.index) {
        button.setAttribute("aria-current", "true");
      }
      button.addEventListener("click", function () {
        showQuestion(index, true);
      });
      return button;
    });
    elements.navigator.replaceChildren.apply(elements.navigator, buttons);

    const answered = state.questions.filter(isAnswered).length;
    const flagged = state.questions.filter(function (question) {
      return question.is_flagged;
    }).length;
    elements.progress.textContent =
      answered + " of " + state.questions.length + " answered, " + flagged + " flagged (*).";
  }

  function changeAnswer(question, value) {
    const wasAnswered = isAnswered(question);
    question.submitted_answer = value;
    state.unsaved.set(question.question_id, value);
    elements["save-status"].textContent = "Saving...";
    scheduleSave(SAVE_DELAY_MS);
    if (wasAnswered !== isAnswered(question)) {
      renderNavigator();
    }
  }

  const OFFLINE_MESSAGE = "You're offline. Answers will save when you reconnect.";

  function clockTime(date) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function scheduleSave(delay) {
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(save, delay);
  }

  function unsavedResponses() {
    return Array.from(state.unsaved, function (entry) {
      return { question_id: entry[0], submitted_answer: entry[1] };
    });
  }

  async function save() {
    if (state.saving || state.finished || !state.unsaved.size) {
      return;
    }
    state.saving = true;
    const sent = new Map(state.unsaved);
    try {
      const data = await api("PUT", attemptPath("autosave/"), { responses: unsavedResponses() });
      setRemaining(data.remaining_seconds);
      // Keep anything the student changed while this request was running.
      sent.forEach(function (value, questionId) {
        if (state.unsaved.get(questionId) === value) {
          state.unsaved.delete(questionId);
        }
      });
      if (state.unsaved.size) {
        scheduleSave(SAVE_DELAY_MS);
      } else {
        elements["save-status"].textContent = "All answers saved at " + clockTime(new Date());
      }
    } catch (error) {
      if (error.status === 410) {
        finish("Time is up", "Your exam was submitted automatically with the answers saved before the deadline.");
      } else if (!handleSessionLoss(error)) {
        // Offline, the "online" event saves straight away on reconnecting.
        elements["save-status"].textContent = navigator.onLine
          ? "Not saved yet. Retrying..."
          : OFFLINE_MESSAGE;
        scheduleSave(SAVE_RETRY_MS);
      }
    } finally {
      state.saving = false;
    }
  }

  async function toggleFlag() {
    const question = currentQuestion();
    const flagged = !question.is_flagged;
    clearError();
    try {
      await api("POST", attemptPath("questions/" + question.question_id + "/flag/"), {
        is_flagged: flagged,
      });
      question.is_flagged = flagged;
      showQuestion(state.index, false);
      elements["flag-button"].focus();
    } catch (error) {
      if (error.status === 410) {
        syncTimer();
      } else if (!handleSessionLoss(error)) {
        showError("The flag couldn't be saved. Please try again.");
      }
    }
  }

  async function submitExam() {
    const unanswered = state.questions.length - state.questions.filter(isAnswered).length;
    const warning = unanswered ? unanswered + " unanswered. " : "";
    if (!window.confirm(warning + "Submit your exam? You can't change your answers afterwards.")) {
      return;
    }

    clearError();
    elements["submit-button"].disabled = true;
    try {
      const data = await api("POST", attemptPath("submit/"), { responses: unsavedResponses() });
      if (data.reason === "TIMEOUT") {
        finish("Time is up", "Your exam was submitted automatically with the answers saved before the deadline.");
      } else {
        finish("Exam submitted", "Your answers have been recorded.");
      }
    } catch (error) {
      elements["submit-button"].disabled = false;
      if (handleSessionLoss(error)) {
        return;
      }
      if (error instanceof ApiError) {
        // The server answered but refused, so a connection problem isn't the cause.
        showError(
          "Your exam couldn't be submitted: " + error.message +
            " Reload the page to check your answers, then try again."
        );
      } else {
        showError("Your exam couldn't be submitted. Check your connection and try again.");
      }
    }
  }

  function finish(heading, message) {
    if (state.finished) {
      return;
    }
    state.finished = true;
    stopTimers();
    state.unsaved.clear();
    clearError();
    elements["exam-sitting"].hidden = true;
    elements["exam-finished"].hidden = false;
    elements["finished-heading"].textContent = heading;
    elements["finished-message"].textContent = message;
    elements["finished-heading"].focus();
  }

  elements["start-button"].addEventListener("click", startExam);
  elements["previous-button"].addEventListener("click", function () {
    showQuestion(state.index - 1, true);
  });
  elements["next-button"].addEventListener("click", function () {
    showQuestion(state.index + 1, true);
  });
  elements["flag-button"].addEventListener("click", toggleFlag);
  elements["submit-button"].addEventListener("click", submitExam);

  // Reconnecting: save at once and fetch the remaining time, which kept
  // running on the server while the student was offline.
  window.addEventListener("online", function () {
    if (state.attemptId === null || state.finished) {
      return;
    }
    elements["save-status"].textContent = state.unsaved.size ? "Saving..." : "All answers saved";
    save();
    syncTimer();
  });
  window.addEventListener("offline", function () {
    if (state.attemptId !== null && !state.finished) {
      elements["save-status"].textContent = OFFLINE_MESSAGE;
    }
  });
  // Switching tabs or closing the laptop: send what's pending first.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      save();
    }
  });

  window.addEventListener("beforeunload", function (event) {
    if (state.unsaved.size && !state.finished) {
      event.preventDefault();
    }
  });
})();
