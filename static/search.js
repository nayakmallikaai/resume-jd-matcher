"use strict";

const MAX_CHARS = 500;
const MIN_CHARS = 10;

const jdInput       = document.getElementById("jdInput");
const charCounter   = document.getElementById("charCounter");
const errorBox      = document.getElementById("errorBox");
const errorMsg      = document.getElementById("errorMsg");
const searchBtn     = document.getElementById("searchBtn");
const resultsSection = document.getElementById("resultsSection");
const resultsHeader = document.getElementById("resultsHeader");
const resultList    = document.getElementById("resultList");

// ---------------------------------------------------------------------------
// Character counter
// ---------------------------------------------------------------------------

jdInput.addEventListener("input", () => {
  const len = jdInput.value.length;
  charCounter.textContent = `${len} / ${MAX_CHARS}`;
  charCounter.className = "char-counter" + (len > 480 ? " warn" : "") + (len >= MAX_CHARS ? " over" : "");
  clearError();
  resultsSection.style.display = "none";
});

// ---------------------------------------------------------------------------
// Error helpers
// ---------------------------------------------------------------------------

function showError(msg) {
  errorMsg.textContent = msg;
  errorBox.classList.add("visible");
  jdInput.classList.add("error");
}

function clearError() {
  errorBox.classList.remove("visible");
  errorMsg.textContent = "";
  jdInput.classList.remove("error");
}

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

function setLoading(loading) {
  if (loading) {
    searchBtn.disabled = true;
    searchBtn.innerHTML = '<span class="spinner" aria-hidden="true"></span>Searching…';
  } else {
    searchBtn.disabled = false;
    searchBtn.textContent = "Find Matching Candidates";
  }
}

// ---------------------------------------------------------------------------
// Result rendering — all user-controlled strings via textContent
// ---------------------------------------------------------------------------

function renderResults(results) {
  resultList.textContent = "";
  resultsSection.style.display = "block";

  if (!results || results.length === 0) {
    resultsHeader.textContent = "No matches found";
    const empty = document.createElement("div");
    empty.className = "no-results";
    empty.textContent = "No candidates matched this job description. Try ingesting more resumes.";
    resultList.appendChild(empty);
    return;
  }

  resultsHeader.textContent = `Top ${results.length} matching candidate${results.length !== 1 ? "s" : ""}`;

  for (const c of results) {
    const item = document.createElement("div");
    item.className = "result-item";

    // Rank badge
    const badge = document.createElement("div");
    badge.className = "rank-badge" + (c.rank <= 3 ? " top3" : "");
    badge.textContent = `#${c.rank}`;

    // Body
    const body = document.createElement("div");
    body.className = "result-body";

    const name = document.createElement("div");
    name.className = "result-name";
    name.textContent = c.name || "Unknown";

    const email = document.createElement("div");
    email.className = "result-email";
    email.textContent = c.email || "No email on file";

    const reason = document.createElement("div");
    reason.className = "result-reason";
    reason.textContent = c.reason || "";

    const summary = document.createElement("div");
    summary.className = "result-summary";
    summary.textContent = c.summary || "";

    body.appendChild(name);
    body.appendChild(email);
    body.appendChild(reason);
    body.appendChild(summary);

    item.appendChild(badge);
    item.appendChild(body);
    resultList.appendChild(item);
  }
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

async function doSearch() {
  clearError();

  const jd = jdInput.value.trim();

  if (jd.length < MIN_CHARS) {
    showError(`Job description must be at least ${MIN_CHARS} characters.`);
    return;
  }

  if (jd.length > MAX_CHARS) {
    showError(`Job description must be ${MAX_CHARS} characters or fewer.`);
    return;
  }

  setLoading(true);
  resultsSection.style.display = "none";

  try {
    const response = await fetch("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ job_description: jd }),
    });

    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("Unexpected response from server.");
    }

    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "Search failed.";
      throw new Error(detail);
    }

    renderResults(data.results);
  } catch (err) {
    showError(err.message || "Network error. Please try again.");
  } finally {
    setLoading(false);
  }
}

searchBtn.addEventListener("click", doSearch);

jdInput.addEventListener("keydown", (e) => {
  // Ctrl+Enter or Cmd+Enter submits
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    doSearch();
  }
});
