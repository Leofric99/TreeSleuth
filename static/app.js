// Simple GEDCOM validation app
const elements = {
  gedcomFile: document.querySelector("#gedcomFile"),
  fileInfo: document.querySelector("#fileInfo"),
  fileName: document.querySelector("#fileName"),
  validateBtn: document.querySelector("#validateBtn"),
  clearBtn: document.querySelector("#clearBtn"),
  validationStatus: document.querySelector("#validationStatus"),
  errorMessage: document.querySelector("#errorMessage"),
  resultsSection: document.querySelector("#resultsSection"),
  resultsSummary: document.querySelector("#resultsSummary"),
  individualCount: document.querySelector("#individualCount"),
  familyCount: document.querySelector("#familyCount"),
  errorCount: document.querySelector("#errorCount"),
  warningCount: document.querySelector("#warningCount"),
  issuesList: document.querySelector("#issuesList"),
};

let selectedFile = null;

function showError(message) {
  elements.errorMessage.textContent = message;
  elements.errorMessage.classList.remove("hidden");
}

function clearError() {
  elements.errorMessage.textContent = "";
  elements.errorMessage.classList.add("hidden");
}

function showFileSelected(file) {
  selectedFile = file;
  elements.fileName.textContent = file.name;
  elements.fileInfo.classList.remove("hidden");
  clearError();
}

function clearFile() {
  selectedFile = null;
  elements.gedcomFile.value = "";
  elements.fileInfo.classList.add("hidden");
  elements.resultsSection.classList.add("hidden");
  elements.validationStatus.textContent = "";
  clearError();
}

function setValidationStatus(message) {
  elements.validationStatus.textContent = message;
}

function displayResults(result) {
  // Update summary
  const fileText = selectedFile ? `Validated: ${selectedFile.name}` : "Validation complete";
  elements.resultsSummary.textContent = fileText;
  
  // Update counts
  elements.individualCount.textContent = result.total_individuals || 0;
  elements.familyCount.textContent = result.total_families || 0;
  elements.errorCount.textContent = result.errors || 0;
  elements.warningCount.textContent = result.warnings || 0;

  // Clear and populate issues list
  elements.issuesList.innerHTML = "";

  if (!result.issues || result.issues.length === 0) {
    const noIssuesDiv = document.createElement("div");
    noIssuesDiv.className = "rounded-lg border border-teal-900/50 bg-teal-950/20 p-4";
    noIssuesDiv.innerHTML = `
      <p class="text-sm font-medium text-teal-200">✓ No issues found</p>
      <p class="mt-1 text-xs text-teal-400">Your family tree is logically consistent.</p>
    `;
    elements.issuesList.appendChild(noIssuesDiv);
  } else {
    // Group issues by category
    const byCategory = {};
    for (const issue of result.issues) {
      if (!byCategory[issue.category]) {
        byCategory[issue.category] = [];
      }
      byCategory[issue.category].push(issue);
    }

    // Display by category
    for (const [category, issues] of Object.entries(byCategory)) {
      const categoryDiv = document.createElement("div");
      categoryDiv.className = "rounded-lg border border-slate-700 bg-slate-950/50 p-4";
      
      const categoryTitle = document.createElement("h3");
      categoryTitle.className = "font-medium text-slate-200 mb-3";
      categoryTitle.textContent = formatCategoryName(category) + ` (${issues.length})`;
      categoryDiv.appendChild(categoryTitle);

      const issuesList = document.createElement("ul");
      issuesList.className = "space-y-2";

      for (const issue of issues) {
        const issueItem = document.createElement("li");
        issueItem.className = `rounded px-3 py-2 text-sm ${
          issue.severity === "error"
            ? "border-l-4 border-rose-600 bg-rose-950/30 text-rose-100"
            : "border-l-4 border-amber-600 bg-amber-950/30 text-amber-100"
        }`;

        const personName = document.createElement("strong");
        personName.textContent = issue.person_name || "Unknown";

        const issueText = document.createTextNode(": " + issue.message);

        issueItem.appendChild(personName);
        issueItem.appendChild(issueText);

        if (issue.details) {
          const details = document.createElement("div");
          details.className = "mt-1 text-xs opacity-80 font-mono";
          details.textContent = JSON.stringify(issue.details, null, 2)
            .split("\n")
            .slice(0, 3)
            .join(" ");
          issueItem.appendChild(details);
        }

        issuesList.appendChild(issueItem);
      }

      categoryDiv.appendChild(issuesList);
      elements.issuesList.appendChild(categoryDiv);
    }
  }

  // Show results section
  elements.resultsSection.classList.remove("hidden");
}

function formatCategoryName(category) {
  const names = {
    anachronism: "Anachronisms",
    time_travel: "Time Travel",
    lifespan: "Lifespan Issues",
    marriage: "Marriage Timing",
    location: "Location Issues",
  };
  return names[category] || category;
}

async function validateGedcom() {
  if (!selectedFile) {
    showError("No file selected");
    return;
  }

  setValidationStatus("Validating...");
  elements.validateBtn.disabled = true;

  try {
    // Create form data with the file
    const formData = new FormData();
    formData.append("file", selectedFile);

    // Make request to new upload/validate endpoint
    const response = await fetch("/api/validate-gedcom-upload", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `Validation failed (${response.status})`);
    }

    const result = await response.json();
    displayResults(result);
    setValidationStatus(`Validation complete: ${result.issues_found} issues found`);
  } catch (error) {
    showError(`Validation error: ${error.message}`);
    setValidationStatus("");
  } finally {
    elements.validateBtn.disabled = false;
  }
}

// File input handling
elements.gedcomFile.addEventListener("change", (e) => {
  if (e.target.files && e.target.files[0]) {
    showFileSelected(e.target.files[0]);
  }
});

// Drag and drop
const dropZone = document.querySelector('[for="gedcomFile"]').parentElement;
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("bg-slate-800");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("bg-slate-800");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("bg-slate-800");
  if (e.dataTransfer.files && e.dataTransfer.files[0]) {
    elements.gedcomFile.files = e.dataTransfer.files;
    showFileSelected(e.dataTransfer.files[0]);
  }
});

// Button handling
elements.validateBtn.addEventListener("click", validateGedcom);
elements.clearBtn.addEventListener("click", clearFile);
