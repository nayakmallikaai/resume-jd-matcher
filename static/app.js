"use strict";

const MAX_BYTES = 150 * 1024; // 150 KB
const ALLOWED_MIME = "application/pdf";
const ALLOWED_EXT = ".pdf";

// DOM refs
const dropZone  = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const fileInfo  = document.getElementById("fileInfo");
const fileName  = document.getElementById("fileName");
const fileSize  = document.getElementById("fileSize");
const removeBtn = document.getElementById("removeBtn");
const errorBox  = document.getElementById("errorBox");
const errorMsg  = document.getElementById("errorMsg");
const uploadBtn = document.getElementById("uploadBtn");
const resultCard = document.getElementById("resultCard");
const resultGrid = document.getElementById("resultGrid");
const resultTags = document.getElementById("resultTags");

let selectedFile = null;

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function validateFile(file) {
  // Extension check
  if (!file.name.toLowerCase().endsWith(ALLOWED_EXT)) {
    return "Only PDF files are accepted.";
  }
  // MIME type check (browser-supplied — treated as a first-pass hint, not trusted alone)
  if (file.type && file.type !== ALLOWED_MIME) {
    return "Only PDF files are accepted.";
  }
  // Size check
  if (file.size > MAX_BYTES) {
    const kb = (file.size / 1024).toFixed(1);
    return `File is ${kb} KB — must be under 150 KB.`;
  }
  return null; // valid
}

// ---------------------------------------------------------------------------
// UI state helpers
// ---------------------------------------------------------------------------

function showError(msg) {
  errorMsg.textContent = msg; // textContent: no XSS risk
  errorBox.classList.add("visible");
}

function clearError() {
  errorBox.classList.remove("visible");
  errorMsg.textContent = "";
}

function setFile(file) {
  selectedFile = file;
  fileName.textContent = file.name;
  fileSize.textContent = `${(file.size / 1024).toFixed(1)} KB`;
  fileInfo.classList.add("visible");
  dropZone.classList.add("has-file");
  uploadBtn.disabled = false;
  clearError();
  resultCard.classList.remove("visible");
}

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  fileInfo.classList.remove("visible");
  dropZone.classList.remove("has-file");
  uploadBtn.disabled = true;
  clearError();
}

function setLoading(loading) {
  if (loading) {
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<span class="spinner" aria-hidden="true"></span>Processing…';
  } else {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Upload Resume";
  }
}

// ---------------------------------------------------------------------------
// Result rendering — all values set via textContent (no innerHTML with data)
// ---------------------------------------------------------------------------

function renderResult(data) {
  resultGrid.textContent = "";
  resultTags.textContent = "";

  const fields = [
    ["ID",          data.resume_id],
    ["Name",        data.name],
    ["Seniority",   data.seniority],
    ["Experience",  data.total_years != null ? `${data.total_years} yrs` : "—"],
    ["Location",    data.location],
    ["Remote",      data.open_to_remote != null ? (data.open_to_remote ? "Yes" : "No") : "—"],
    ["Employment",  data.employment_type],
    ["Chunks",      data.experience_chunks_stored],
    ["Summary",     data.summary],
  ];

  for (const [key, val] of fields) {
    const k = document.createElement("span");
    k.className = "result-key";
    k.textContent = key;

    const v = document.createElement("span");
    v.className = "result-val";
    v.textContent = val ?? "—";

    resultGrid.appendChild(k);
    resultGrid.appendChild(v);
  }

  for (const topic of (data.key_topics || [])) {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = topic; // safe: textContent
    resultTags.appendChild(tag);
  }

  resultCard.classList.add("visible");
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

async function uploadFile() {
  if (!selectedFile) return;

  const validationError = validateFile(selectedFile);
  if (validationError) {
    showError(validationError);
    return;
  }

  setLoading(true);
  clearError();
  resultCard.classList.remove("visible");

  const form = new FormData();
  // Sanitize the filename before appending to avoid sending path components
  const safeName = selectedFile.name.replace(/[^a-zA-Z0-9._-]/g, "_");
  form.append("file", selectedFile, safeName);

  try {
    const response = await fetch("/ingest", {
      method: "POST",
      body: form,
      // No Content-Type header — browser sets multipart boundary automatically
      credentials: "same-origin",
    });

    // Parse response as JSON (never eval, never innerHTML)
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("Unexpected response from server.");
    }

    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "Upload failed.";
      throw new Error(detail);
    }

    clearFile();
    renderResult(data);
  } catch (err) {
    // err.message is our own string or a network error — safe to display
    showError(err.message || "Network error. Please try again.");
  } finally {
    setLoading(false);
  }
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;
  const err = validateFile(file);
  if (err) { showError(err); fileInput.value = ""; return; }
  setFile(file);
});

removeBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  clearFile();
});

uploadBtn.addEventListener("click", uploadFile);

// Drag and drop
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (!file) return;
  const err = validateFile(file);
  if (err) { showError(err); return; }
  setFile(file);
});

// Keyboard accessibility for drop zone
dropZone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});
