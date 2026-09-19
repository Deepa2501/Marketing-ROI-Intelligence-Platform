/*
 * copilot.js — Phase 14: Marketing Analyst Copilot.
 * Single source of truth: POST /api/copilot/ask and
 * GET /api/copilot/capabilities. Every answer, metric, and caveat
 * rendered here comes straight from the backend — the frontend never
 * generates or interprets an analytical result.
 *
 * No external AI service, no fake typing delays, no simulated
 * streaming. Responses render as soon as the API returns.
 */

const SUGGESTED_QUESTIONS = [
  "Which campaign type has the highest average ROI?",
  "Which customer segment has the highest revenue?",
  "What is the average ROI?",
  "How many campaigns have negative ROI?",
  "What does the Social Media vs Paid Ads A/B test show?",
  "What is the current revenue outlook?",
  "What is the ROI model's R²?",
  "Is the dataset ready for analysis?",
  "How should ₹1 lakh be allocated across campaign types?",
];

document.addEventListener("DOMContentLoaded", () => {
  renderSuggestedQuestions();
  loadCapabilities();
  bindControls();
});

function bindControls() {
  document.getElementById("copilot-ask-btn").addEventListener("click", submitQuestion);
  document.getElementById("copilot-clear-btn").addEventListener("click", clearConversation);
  document.getElementById("copilot-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitQuestion();
  });
}

function renderSuggestedQuestions() {
  const el = document.getElementById("suggested-questions");
  el.innerHTML = SUGGESTED_QUESTIONS.map(
    (q) => `<button type="button" class="suggested-question">${escapeHtml(q)}</button>`
  ).join("");

  el.querySelectorAll(".suggested-question").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("copilot-input").value = btn.textContent;
      submitQuestion();
    });
  });
}

async function loadCapabilities() {
  const el = document.getElementById("capability-list");
  try {
    const data = await apiFetch("/api/copilot/capabilities");
    el.innerHTML = (data.capabilities || [])
      .map((c) => `<div class="capability-item"><strong>${escapeHtml(c.category)}</strong> — ${escapeHtml(c.source_area)}</div>`)
      .join("");
  } catch (err) {
    el.innerHTML = '<div class="capability-item">Capabilities unavailable.</div>';
  }
}

/* ============================================================
   ASK
   ============================================================ */

async function submitQuestion() {
  const input = document.getElementById("copilot-input");
  const errorEl = document.getElementById("copilot-error");
  const askBtn = document.getElementById("copilot-ask-btn");
  const question = input.value.trim();

  errorEl.hidden = true;
  if (!question) {
    errorEl.textContent = "Please enter a question.";
    errorEl.hidden = false;
    return;
  }

  appendUserMessage(question);
  input.value = "";
  askBtn.disabled = true;
  askBtn.textContent = "Asking…";

  const pending = appendAssistantPlaceholder();

  try {
    const data = await apiFetch("/api/copilot/ask", { method: "POST", body: { question }, useCache: false });
    renderAssistantAnswer(pending, data);
  } catch (err) {
    renderAssistantError(pending, err.friendlyMessage || "The Copilot could not process that question.");
  } finally {
    askBtn.disabled = false;
    askBtn.textContent = "Ask";
  }
}

async function clearConversation() {
  const thread = document.getElementById("copilot-thread");
  try {
    await apiFetch("/api/copilot/reset", { method: "POST", body: {}, useCache: false });
  } catch (err) {
    // Clearing the visible thread is still worthwhile even if the
    // server-side context reset failed.
  }
  thread.innerHTML = `
    <div class="copilot-msg copilot-msg--assistant">
      <div class="copilot-msg__role">Copilot</div>
      <div class="copilot-msg__body">Conversation cleared. Ask a new question about the connected marketing dataset.</div>
    </div>`;
}

/* ============================================================
   MESSAGE RENDERING
   ============================================================ */

function appendUserMessage(question) {
  const thread = document.getElementById("copilot-thread");
  const node = document.createElement("div");
  node.className = "copilot-msg copilot-msg--user";
  node.innerHTML = `<div class="copilot-msg__role">You</div><div class="copilot-msg__body">${escapeHtml(question)}</div>`;
  thread.appendChild(node);
  scrollThread();
}

function appendAssistantPlaceholder() {
  const thread = document.getElementById("copilot-thread");
  const node = document.createElement("div");
  node.className = "copilot-msg copilot-msg--assistant";
  node.innerHTML = `<div class="copilot-msg__role">Copilot</div><div class="copilot-msg__body">Checking the platform's analytics…</div>`;
  thread.appendChild(node);
  scrollThread();
  return node;
}

function evidenceBadgeClass(basis) {
  return { OBSERVED: "badge--confidence-high", PREDICTIVE: "badge--confidence-medium", EXPERIMENTAL: "badge--evidence" }[basis] || "badge--confidence-low";
}

function renderAssistantAnswer(node, data) {
  const metrics = data.supporting_metrics && Object.keys(data.supporting_metrics).length
    ? `<div class="copilot-metrics">${escapeHtml(JSON.stringify(data.supporting_metrics, null, 2))}</div>`
    : "";

  const caveats = (data.caveats || []).length
    ? `<ul class="copilot-caveats">${data.caveats.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>`
    : "";

  node.innerHTML = `
    <div class="copilot-msg__role">Copilot</div>
    <div class="copilot-msg__body">${escapeHtml(data.answer)}</div>
    <div class="copilot-meta">
      <div class="copilot-meta__row">
        <span class="badge ${evidenceBadgeClass(data.evidence_basis)}">Evidence: ${escapeHtml(data.evidence_basis)}</span>
        <span class="badge badge--evidence">Source: ${escapeHtml(data.source_area)}</span>
        <span class="badge badge--confidence-low">${escapeHtml(data.intent)}</span>
      </div>
      ${metrics}
      ${caveats}
    </div>`;
  scrollThread();
}

function renderAssistantError(node, message) {
  node.innerHTML = `<div class="copilot-msg__role">Copilot</div><div class="copilot-msg__body">${escapeHtml(message)}</div>`;
  scrollThread();
}

function scrollThread() {
  const thread = document.getElementById("copilot-thread");
  thread.scrollTop = thread.scrollHeight;
}

/**
 * Escape all user- and API-supplied text before inserting into the
 * DOM. Answers are plain analytical text, never trusted HTML.
 */
function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
