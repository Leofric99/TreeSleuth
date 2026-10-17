const state = {
  people: new Map(),
  surnameMappings: {},
  eventSource: null,
  activeRunId: null,
  prepared: false,
  generationInProgress: false,
  selectedPersonIds: new Set(),
  expandedSurnameGroups: new Set(),
};

const elements = {
  serviceStatus: document.querySelector("#serviceStatus"),
  modelSelect: document.querySelector("#modelSelect"),
  visionModelSelect: document.querySelector("#visionModelSelect"),
  directoryPath: document.querySelector("#directoryPath"),
  refreshModels: document.querySelector("#refreshModels"),
  previewDirectory: document.querySelector("#previewDirectory"),
  startPipeline: document.querySelector("#startPipeline"),
  peopleGroups: document.querySelector("#peopleGroups"),
  selectAllPeople: document.querySelector("#selectAllPeople"),
  generateSelected: document.querySelector("#generateSelected"),
  generateAll: document.querySelector("#generateAll"),
  surnameMappingForm: document.querySelector("#surnameMappingForm"),
  surnameVariant: document.querySelector("#surnameVariant"),
  displaySurname: document.querySelector("#displaySurname"),
  saveSurnameMapping: document.querySelector("#saveSurnameMapping"),
  surnameMappingMessage: document.querySelector("#surnameMappingMessage"),
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

let previewHasScans = false;

function fillModelSelect(select, placeholder, models) {
  select.replaceChildren();
  select.add(new Option(placeholder, ""));
  for (const model of models) {
    select.add(new Option(model, model));
  }
  select.disabled = false;
}

function disableModelSelects(label) {
  for (const select of [elements.modelSelect, elements.visionModelSelect]) {
    select.replaceChildren();
    select.add(new Option(label, ""));
    select.disabled = true;
  }
}

async function checkOllama() {
  clearError();
  elements.refreshModels.disabled = true;
  setPill(elements.serviceStatus, "Checking local model…");
  try {
    const result = await requestJson("/api/system-check");
    if (!result.ollama_available) {
      disableModelSelects("Ollama unavailable");
      setPill(elements.serviceStatus, "Ollama unavailable", "error");
      showError(result.error || "Could not connect to local Ollama.");
      return;
    }
    if (!result.models.length) {
      disableModelSelects("No local models found");
      setPill(elements.serviceStatus, "No local models", "warning");
      elements.actionMessage.textContent = "Install a model in Ollama to continue.";
      return;
    }
    fillModelSelect(elements.modelSelect, "Select a model", result.models);
    fillModelSelect(elements.visionModelSelect, "Select a vision model", result.models);
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
  const needsVision = previewHasScans && !elements.visionModelSelect.value;
  elements.startPipeline.disabled =
    !elements.directoryPath.value.trim() || !elements.modelSelect.value || needsVision;
  if (needsVision && elements.modelSelect.value) {
    elements.actionMessage.textContent = "Select a vision model to transcribe the scanned documents.";
  }
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
    previewHasScans = (result.files_by_type.pdf || 0) + (result.files_by_type.image || 0) > 0;
    elements.actionMessage.textContent = "Folder preview ready. Transcription has not started.";
    updateStartButton();
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

function effectiveSurname(person) {
  if (person.display_surname || person.surname) return person.display_surname || person.surname;
  const nameParts = person.name.trim().split(/\s+/);
  return nameParts[nameParts.length - 1] || "Unknown";
}

function surnameGroupKey(surname) {
  return surname.toLocaleLowerCase();
}

function personCanGenerate(person) {
  return state.prepared
    && !state.generationInProgress
    && !["Parsing Records", "Comparing with GEDCOM", "Writing Biography"].includes(person.status);
}

function renderSurnameMappingControls() {
  const selectedValue = elements.surnameVariant.value;
  const targetValue = elements.displaySurname.value;
  const surnames = [...new Map(
    [...state.people.values()]
      .filter((person) => person.surname)
      .map((person) => [person.surname.toLocaleLowerCase(), person.surname]),
  ).values()].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }));
  const displaySurnames = [...new Set([
    ...surnames,
    ...Object.values(state.surnameMappings),
  ])].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }));
  elements.surnameVariant.replaceChildren(new Option(
    surnames.length ? "Select a spelling" : "Load people to manage surnames",
    "",
  ));
  for (const surname of surnames) {
    elements.surnameVariant.add(new Option(surname, surname));
  }
  elements.displaySurname.replaceChildren(new Option("Choose the surname to keep", ""));
  for (const surname of displaySurnames) {
    elements.displaySurname.add(new Option(surname, surname));
  }
  if (surnames.includes(selectedValue)) elements.surnameVariant.value = selectedValue;
  if (displaySurnames.includes(targetValue)) elements.displaySurname.value = targetValue;
  elements.surnameVariant.disabled = !state.activeRunId || !surnames.length;
  elements.displaySurname.disabled = !state.activeRunId || displaySurnames.length < 2;
  elements.saveSurnameMapping.disabled = !state.activeRunId
    || !selectedValue
    || !targetValue
    || selectedValue.toLocaleLowerCase() === targetValue.toLocaleLowerCase();
  elements.generateAll.disabled = !state.prepared || state.generationInProgress || !state.people.size;
  const eligiblePeople = [...state.people.values()].filter(personCanGenerate);
  const selectedCount = eligiblePeople.filter((person) => state.selectedPersonIds.has(person.id)).length;
  elements.selectAllPeople.disabled = !eligiblePeople.length;
  elements.selectAllPeople.checked = eligiblePeople.length > 0 && selectedCount === eligiblePeople.length;
  elements.selectAllPeople.indeterminate = selectedCount > 0 && selectedCount < eligiblePeople.length;
  elements.generateSelected.disabled = selectedCount === 0 || state.generationInProgress;
  elements.generateSelected.textContent = selectedCount
    ? `Generate selected stories (${selectedCount})`
    : "Generate selected stories";
}

function renderPeople() {
  elements.peopleGroups.replaceChildren();
  if (!state.people.size) {
    const empty = document.createElement("p");
    empty.className = "py-8 text-center text-slate-500";
    empty.textContent = "No people identified yet.";
    elements.peopleGroups.append(empty);
    renderSurnameMappingControls();
    return;
  }
  const people = [...state.people.values()].sort((left, right) => (
    effectiveSurname(left).localeCompare(effectiveSurname(right), undefined, { sensitivity: "base" })
    || left.name.localeCompare(right.name, undefined, { sensitivity: "base" })
    || left.id.localeCompare(right.id)
  ));
  const groups = new Map();
  for (const person of people) {
    const surname = effectiveSurname(person);
    const surnameKey = surnameGroupKey(surname);
    if (!groups.has(surnameKey)) {
      groups.set(surnameKey, { surname, people: [] });
    }
    groups.get(surnameKey).people.push(person);
  }

  for (const [surnameKey, group] of groups) {
    const details = document.createElement("details");
    details.className = "overflow-hidden rounded-lg border border-slate-800 bg-slate-950/40";
    details.open = state.expandedSurnameGroups.has(surnameKey);
    details.addEventListener("toggle", () => {
      if (details.open) state.expandedSurnameGroups.add(surnameKey);
      else state.expandedSurnameGroups.delete(surnameKey);
    });
    const summary = document.createElement("summary");
    summary.className = "surname-summary cursor-pointer list-none bg-slate-900/70 px-4 py-3 font-semibold text-teal-200";
    const summaryLabel = document.createElement("span");
    summaryLabel.textContent = `${group.surname} (${group.people.length})`;
    summary.append(summaryLabel);
    details.append(summary);
    const tableWrap = document.createElement("div");
    tableWrap.className = "overflow-x-auto";
    const table = document.createElement("table");
    table.className = "w-full min-w-[42rem] text-left text-sm";
    table.innerHTML = `
      <thead class="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
        <tr>
          <th class="w-12 px-4 py-3 font-medium"><span class="sr-only">Select</span></th>
          <th class="py-3 pr-4 font-medium">Name</th>
          <th class="py-3 pr-4 font-medium">Lifespan</th>
          <th class="py-3 pr-4 font-medium">Documents</th>
          <th class="py-3 pr-4 font-medium">Status</th>
          <th class="py-3 font-medium">Actions</th>
        </tr>
      </thead>`;
    const body = document.createElement("tbody");
    for (const person of group.people) {
      const row = document.createElement("tr");
      row.className = "border-b border-slate-800/70 last:border-0";
      const selectCell = document.createElement("td");
      selectCell.className = "px-4 py-3";
      const select = document.createElement("input");
      select.className = "h-4 w-4 accent-teal-400";
      select.type = "checkbox";
      select.checked = state.selectedPersonIds.has(person.id);
      select.disabled = !personCanGenerate(person);
      select.setAttribute("aria-label", `Select ${person.name} for story generation`);
      select.addEventListener("change", () => {
        if (select.checked) state.selectedPersonIds.add(person.id);
        else state.selectedPersonIds.delete(person.id);
        renderSurnameMappingControls();
      });
      selectCell.append(select);
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
      const generate = document.createElement("button");
      generate.className = "button button-secondary mr-2";
      generate.type = "button";
      generate.textContent = "Generate story";
      generate.disabled = !personCanGenerate(person);
      generate.addEventListener("click", () => generateStories(person.id));
      const view = document.createElement("button");
      view.className = "button button-quiet";
      view.type = "button";
      view.textContent = "View";
      view.disabled = person.status !== "Finished" && person.status !== "Failed";
      view.addEventListener("click", () => showPerson(person.id));
      resultCell.append(generate, view);
      row.append(selectCell, nameCell, lifespanCell, docsCell, statusCell, resultCell);
      body.append(row);
    }
    table.append(body);
    tableWrap.append(table);
    details.append(tableWrap);
    elements.peopleGroups.append(details);
  }
  renderSurnameMappingControls();
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
  if (!snapshot.parent_run_id) state.people.clear();
  for (const person of snapshot.people || []) {
    state.people.set(person.id, person);
  }
  if (snapshot.surname_mappings) state.surnameMappings = snapshot.surname_mappings;
  if (!snapshot.parent_run_id && snapshot.status === "completed") state.prepared = true;
  renderPeople();
}

async function refreshRun(runId) {
  const snapshot = await requestJson(`/api/runs/${encodeURIComponent(runId)}`);
  updateFromSnapshot(snapshot);
  if (snapshot.status === "completed") setPill(elements.runStatus, "Finished", "success");
  if (snapshot.status === "failed") setPill(elements.runStatus, "Failed", "error");
}

function connectToRun(run, runKind = "preparation") {
  if (state.eventSource) state.eventSource.close();
  if (runKind === "preparation") state.activeRunId = run.run_id;
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
        if (runKind === "preparation" && name === "complete") state.prepared = true;
        if (runKind === "generation") {
          state.generationInProgress = false;
          renderPeople();
        }
        if (name === "error") {
          setPill(elements.runStatus, "Failed", "error");
          showError(detail.message);
          elements.actionMessage.textContent = runKind === "generation"
            ? "Story generation failed. Review the errors before retrying."
            : "";
        } else {
          setPill(elements.runStatus, "Finished", "success");
          clearError();
          elements.actionMessage.textContent = runKind === "generation"
            ? "Story generation finished. Review each person's status and results."
            : "Document preparation is complete. Generate stories when ready.";
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
  state.surnameMappings = {};
  state.activeRunId = null;
  state.prepared = false;
  state.generationInProgress = false;
  state.selectedPersonIds.clear();
  state.expandedSurnameGroups.clear();
  renderSurnameMappingControls();
  renderPeople();
  try {
    const run = await requestJson("/api/run-pipeline", {
      method: "POST",
      body: JSON.stringify({
        path: elements.directoryPath.value.trim(),
        model: elements.modelSelect.value,
        vision_model: elements.visionModelSelect.value || null,
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

async function saveSurnameMapping(event) {
  event.preventDefault();
  const surname = elements.surnameVariant.value;
  const displaySurname = elements.displaySurname.value;
  if (!surname || !displaySurname) {
    elements.surnameMappingMessage.textContent = "Choose a surname and enter a display surname.";
    return;
  }
  elements.saveSurnameMapping.disabled = true;
  elements.surnameMappingMessage.textContent = "Saving surname mapping…";
  try {
    const mappings = { ...state.surnameMappings, [surname]: displaySurname };
    const result = await requestJson(`/api/runs/${encodeURIComponent(state.activeRunId)}/surname-mappings`, {
      method: "PUT",
      body: JSON.stringify({ mappings }),
    });
    state.surnameMappings = result.mappings;
    for (const person of state.people.values()) {
      if (person.surname) {
        person.display_surname = result.mappings[person.surname.toLocaleLowerCase()] || person.surname;
      }
    }
    elements.surnameMappingMessage.textContent = `${surname} will be displayed as ${displaySurname}.`;
    renderPeople();
  } catch (error) {
    elements.surnameMappingMessage.textContent = "";
    showError(error.message);
  } finally {
    renderSurnameMappingControls();
  }
}

async function generateStories(personId = null, generateAll = false) {
  if (!state.activeRunId || !state.prepared || state.generationInProgress) return;
  const selectedPersonIds = personId || generateAll
    ? null
    : [...state.selectedPersonIds].filter((id) => {
      const person = state.people.get(id);
      return person && personCanGenerate(person);
    });
  if (!personId && !generateAll && !selectedPersonIds?.length) return;
  clearError();
  state.generationInProgress = true;
  state.selectedPersonIds.clear();
  renderPeople();
  setPill(elements.runStatus, "Generating stories", "warning");
  elements.actionMessage.textContent = personId
    ? "Generating the selected life story…"
    : "Generating life stories for everyone…";
  try {
    const run = await requestJson(`/api/runs/${encodeURIComponent(state.activeRunId)}/generate`, {
      method: "POST",
      body: JSON.stringify(
        personId
          ? { person_id: personId }
          : generateAll
            ? {}
            : { person_ids: selectedPersonIds },
      ),
    });
    connectToRun(run, "generation");
  } catch (error) {
    state.generationInProgress = false;
    showError(error.message);
    elements.actionMessage.textContent = "";
    renderPeople();
  }
}

elements.refreshModels.addEventListener("click", checkOllama);
elements.previewDirectory.addEventListener("click", previewDirectory);
elements.startPipeline.addEventListener("click", startPipeline);
elements.generateAll.addEventListener("click", () => generateStories(null, true));
elements.generateSelected.addEventListener("click", () => generateStories());
elements.selectAllPeople.addEventListener("change", () => {
  for (const person of state.people.values()) {
    if (!personCanGenerate(person)) continue;
    if (elements.selectAllPeople.checked) state.selectedPersonIds.add(person.id);
    else state.selectedPersonIds.delete(person.id);
  }
  renderPeople();
});
elements.surnameMappingForm.addEventListener("submit", saveSurnameMapping);
elements.surnameVariant.addEventListener("change", () => {
  const selected = elements.surnameVariant.value;
  const displaySurname = selected
    ? state.surnameMappings[selected.toLocaleLowerCase()] || selected
    : "";
  elements.displaySurname.value = displaySurname;
  renderSurnameMappingControls();
});
elements.displaySurname.addEventListener("change", renderSurnameMappingControls);
elements.directoryPath.addEventListener("input", () => {
  previewHasScans = false;
  updateStartButton();
});
elements.modelSelect.addEventListener("change", updateStartButton);
elements.visionModelSelect.addEventListener("change", updateStartButton);
elements.clearLog.addEventListener("click", () => elements.eventFeed.replaceChildren());
elements.closeResult.addEventListener("click", () => elements.resultPanel.classList.add("hidden"));
checkOllama();
