const state = {
  people: new Map(),
  eventSource: null,
  activeRunId: null,
};

const elements = {
  serviceStatus: document.querySelector("#serviceStatus"),
  modelSelect: document.querySelector("#modelSelect"),
  directoryPath: document.querySelector("#directoryPath"),
  refreshModels: document.querySelector("#refreshModels"),
  previewDirectory: document.querySelector("#previewDirectory"),
  startPipeline: document.querySelector("#startPipeline"),
  previewSummary: document.querySelector("#previewSummary"),
  actionMessage: document.querySelector("#actionMessage"),
  errorMessage: document.querySelector("#errorMessage"),
  runStatus: document.querySelector("#runStatus"),
  peopleRows: document.querySelector("#peopleRows"),
  eventFeed: document.querySelector("#eventFeed"),
  clearLog: document.querySelector("#clearLog"),
  resultPanel: document.querySelector("#resultPanel"),
  resultTitle: document.querySelector("#resultTitle"),
  biographyText: document.querySelector("#biographyText"),
  conflictList: document.querySelector("#conflictList"),
  closeResult: document.querySelector("#closeResult"),
};

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorMessage.classList.remove("hidden");
}

function clearError() {
  elements.errorMessage.textContent = "";
  elements.errorMessage.classList.add("hidden");
}

function setPill(element, text, kind = "neutral") {
  element.textContent = text;
  element.className = `status-pill status-${kind}`;
}

function appendLog(message, kind = "stage") {
  const entry = document.createElement("li");
  const time = new Date().toLocaleTimeString();
  entry.textContent = `[${time}] ${message}`;
  if (kind === "warning" || kind === "error" || kind === "complete") {
    entry.classList.add(`event-${kind}`);
  }
  elements.eventFeed.append(entry);
  elements.eventFeed.scrollTop = elements.eventFeed.scrollHeight;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || data.error || `Request failed (${response.status})`);
  }
  return data;
}

async function checkOllama() {
  clearError();
  elements.refreshModels.disabled = true;
  setPill(elements.serviceStatus, "Checking local model…");
  try {
    const result = await requestJson("/api/system-check");
    elements.modelSelect.replaceChildren();
    if (!result.ollama_available) {
      elements.modelSelect.add(new Option("Ollama unavailable", ""));
      elements.modelSelect.disabled = true;
      setPill(elements.serviceStatus, "Ollama unavailable", "error");
      showError(result.error || "Could not connect to local Ollama.");
      return;
    }
    if (!result.models.length) {
      elements.modelSelect.add(new Option("No local models found", ""));
      elements.modelSelect.disabled = true;
      setPill(elements.serviceStatus, "No local models", "warning");
      elements.actionMessage.textContent = "Install a model in Ollama to continue.";
      return;
    }
    elements.modelSelect.add(new Option("Select a model", ""));
    for (const model of result.models) {
      elements.modelSelect.add(new Option(model, model));
    }
    elements.modelSelect.disabled = false;
    elements.actionMessage.textContent = "";
    setPill(elements.serviceStatus, "Local Ollama ready", "success");
  } catch (error) {
    setPill(elements.serviceStatus, "System check failed", "error");
    showError(error.message);
  } finally {
    elements.refreshModels.disabled = false;
    updateStartButton();
  }
}

function updateStartButton() {
  elements.startPipeline.disabled = !elements.directoryPath.value.trim() || !elements.modelSelect.value;
}

function renderPreview(summary) {
  const entries = [
    ["GEDCOM trees", summary.gedcom_files],
    ["Documents", summary.document_files],
    ["File types", Object.keys(summary.files_by_type).length],
    ["Baseline", summary.has_gedcom_baseline ? "Found" : "Not found"],
  ];
  elements.previewSummary.replaceChildren();
  for (const [label, value] of entries) {
    const card = document.createElement("div");
    card.className = "rounded-lg border border-slate-800 bg-slate-950/60 p-3";
    const caption = document.createElement("p");
    caption.className = "text-xs text-slate-500";
    caption.textContent = label;
    const count = document.createElement("p");
    count.className = "mt-1 font-semibold text-slate-100";
    count.textContent = String(value);
    card.append(caption, count);
    elements.previewSummary.append(card);
  }
  elements.previewSummary.classList.remove("hidden");
  elements.previewSummary.classList.add("grid");
}

async function previewDirectory() {
  clearError();
  elements.previewDirectory.disabled = true;
  elements.actionMessage.textContent = "Scanning folder structure…";
  try {
    const result = await requestJson("/api/analyze-directory", {
      method: "POST",
      body: JSON.stringify({ path: elements.directoryPath.value.trim() }),
    });
    renderPreview(result);
    elements.actionMessage.textContent = "Folder preview ready. OCR has not started.";
  } catch (error) {
    showError(error.message);
    elements.actionMessage.textContent = "";
  } finally {
    elements.previewDirectory.disabled = false;
  }
}

function lifespan(person) {
  const born = person.birth_year ?? "—";
  const died = person.death_year ?? "—";
  return `${born} – ${died}`;
}

function statusKind(status) {
  if (status === "Finished") return "success";
  if (status === "Failed") return "error";
  if (status === "Idle") return "neutral";
  return "warning";
}

function renderPeople() {
  elements.peopleRows.replaceChildren();
  if (!state.people.size) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "py-8 text-center text-slate-500";
    cell.textContent = "No people identified yet.";
    row.append(cell);
    elements.peopleRows.append(row);
    return;
  }
  for (const person of state.people.values()) {
    const row = document.createElement("tr");
    row.className = "border-b border-slate-800/70 last:border-0";
    const nameCell = document.createElement("td");
    nameCell.className = "py-3 pr-4 font-medium text-slate-200";
    nameCell.textContent = person.name;
    const lifespanCell = document.createElement("td");
    lifespanCell.className = "py-3 pr-4 text-slate-400";
    lifespanCell.textContent = lifespan(person);
    const docsCell = document.createElement("td");
    docsCell.className = "py-3 pr-4 text-slate-400";
    docsCell.textContent = String(person.document_count ?? 0);
    const statusCell = document.createElement("td");
    statusCell.className = "py-3 pr-4";
    const badge = document.createElement("span");
    badge.className = `status-pill status-${statusKind(person.status)}`;
    badge.textContent = person.status;
    statusCell.append(badge);
    const resultCell = document.createElement("td");
    resultCell.className = "py-3";
    const view = document.createElement("button");
    view.className = "button button-quiet";
    view.type = "button";
    view.textContent = "View";
    view.disabled = person.status !== "Finished" && person.status !== "Failed";
    view.addEventListener("click", () => showPerson(person.id));
    resultCell.append(view);
    row.append(nameCell, lifespanCell, docsCell, statusCell, resultCell);
    elements.peopleRows.append(row);
  }
}

function showPerson(personId) {
  const person = state.people.get(personId);
  if (!person) return;
  elements.resultTitle.textContent = person.name;
  elements.biographyText.textContent = person.biography || person.error || "No biography was generated.";
  elements.conflictList.replaceChildren();
  if (!person.conflicts?.length) {
    const item = document.createElement("li");
    item.className = "text-slate-400";
    item.textContent = person.status === "Finished"
      ? "No potential contradictions were reported for evaluated evidence."
      : "Analysis did not complete. Review the status and error above.";
    elements.conflictList.append(item);
  } else {
    for (const conflict of person.conflicts) {
      const item = document.createElement("li");
      item.className = "rounded-lg border border-amber-900/60 bg-slate-950/60 p-3";
      const title = document.createElement("p");
      title.className = "font-medium text-amber-100";
      title.textContent = conflict.outcome === "conflict" ? "Potential conflict" : "Uncertain finding";
      const source = document.createElement("p");
      source.className = "mt-2 text-slate-300";
      source.textContent = `Source: ${conflict.source_claim}`;
      const baseline = document.createElement("p");
      baseline.className = "mt-1 text-slate-400";
      baseline.textContent = `GEDCOM: ${conflict.baseline_claim || "No baseline fact cited"}`;
      const evidence = document.createElement("p");
      evidence.className = "mt-2 text-xs text-slate-500";
      evidence.textContent = `Source ID: ${conflict.source_document_id}; baseline ID: ${conflict.baseline_source_id || "none"}`;
      item.append(title, source, baseline, evidence);
      elements.conflictList.append(item);
    }
  }
  elements.resultPanel.classList.remove("hidden");
  elements.resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function updateFromSnapshot(snapshot) {
  state.people.clear();
  for (const person of snapshot.people || []) {
    state.people.set(person.id, person);
  }
  renderPeople();
}

async function refreshRun(runId) {
  const snapshot = await requestJson(`/api/runs/${encodeURIComponent(runId)}`);
  updateFromSnapshot(snapshot);
  if (snapshot.status === "completed") setPill(elements.runStatus, "Finished", "success");
  if (snapshot.status === "failed") setPill(elements.runStatus, "Failed", "error");
}

function connectToRun(run) {
  if (state.eventSource) state.eventSource.close();
  state.activeRunId = run.run_id;
  setPill(elements.runStatus, "Running", "warning");
  const stream = new EventSource(run.events_url);
  state.eventSource = stream;
  const names = ["stage", "file", "person", "warning", "error", "complete"];
  for (const name of names) {
    stream.addEventListener(name, (event) => {
      const detail = JSON.parse(event.data);
      appendLog(detail.message, name);
      if (name === "person" && detail.payload?.id) {
        state.people.set(detail.payload.id, detail.payload);
        renderPeople();
      }
      if (name === "warning") setPill(elements.runStatus, "Running with warnings", "warning");
      if (name === "error" || name === "complete") {
        stream.close();
        if (name === "error") {
          setPill(elements.runStatus, "Failed", "error");
          showError(detail.message);
        } else {
          setPill(elements.runStatus, "Finished", "success");
          clearError();
        }
        refreshRun(run.run_id).catch((error) => showError(error.message));
      }
    });
  }
  stream.onerror = () => {
    if (stream.readyState === EventSource.CLOSED) {
      appendLog("Event stream closed; pipeline state remains available for refresh.", "warning");
    }
  };
}

async function startPipeline() {
  clearError();
  elements.startPipeline.disabled = true;
  elements.actionMessage.textContent = "Starting local pipeline…";
  state.people.clear();
  renderPeople();
  try {
    const run = await requestJson("/api/run-pipeline", {
      method: "POST",
      body: JSON.stringify({
        path: elements.directoryPath.value.trim(),
        model: elements.modelSelect.value,
      }),
    });
    elements.actionMessage.textContent = `Run ${run.run_id} started.`;
    connectToRun(run);
  } catch (error) {
    showError(error.message);
    elements.actionMessage.textContent = "";
  } finally {
    updateStartButton();
  }
}

elements.refreshModels.addEventListener("click", checkOllama);
elements.previewDirectory.addEventListener("click", previewDirectory);
elements.startPipeline.addEventListener("click", startPipeline);
elements.directoryPath.addEventListener("input", updateStartButton);
elements.modelSelect.addEventListener("change", updateStartButton);
elements.clearLog.addEventListener("click", () => elements.eventFeed.replaceChildren());
elements.closeResult.addEventListener("click", () => elements.resultPanel.classList.add("hidden"));
checkOllama();
