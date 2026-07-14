const state = {
  today: "",
  exportRows: [],
  exportFilter: "ALL",
  exportPage: 1,
  exportPageSize: 10,
};

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function badge(status) {
  return `<span class="badge ${status}">${status}</span>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDateTime(value) {
  if (!value) return "";
  return String(value).replace("T", " ");
}

function setDefaultDates() {
  refreshDateDefaults();
}

function selectedAction() {
  const form = $("#requestForm");
  return new FormData(form).get("action");
}

async function refreshDateDefaults() {
  const form = $("#requestForm");
  const runNum = form.run_num.value.trim();
  const query = new URLSearchParams({ action: selectedAction() });
  if (runNum) query.set("run_num", runNum);
  try {
    const defaults = await api(`/api/defaults?${query.toString()}`);
    form.start_date.value = defaults.start_date || "";
    form.end_date.value = defaults.end_date || "";
    $("#dateRuleMessage").textContent = defaults.message || "";
  } catch (error) {
    $("#dateRuleMessage").textContent = error.message;
  }
}

async function loadSummary() {
  const data = await api("/api/summary");
  state.today = data.today;
  $("#todayLabel").textContent = `Today: ${data.today}`;
  $("#pendingCount").textContent = data.pending || 0;
  $("#willExportNow").textContent = data.will_export_now || 0;
  $("#currentStop").textContent = data.current_stop || 0;
  $("#currentResume").textContent = data.current_resume || 0;
  if (!$("#requestForm").start_date.value) {
    setDefaultDates();
  }
}

async function loadPending() {
  const checker = $("#checkerFilter").value.trim();
  const pod = $("#podFilter").value.trim();
  const query = new URLSearchParams({ status: "pending" });
  if (checker) query.set("checker", checker);
  if (pod) query.set("pod", pod);
  const rows = await api(`/api/requests?${query.toString()}`);
  $("#pendingBody").innerHTML =
    rows
      .map(
        (row) => `
          <tr>
            <td>${row.id}</td>
            <td>${escapeHtml(formatDateTime(row.created_at))}</td>
            <td>${escapeHtml(row.run_num)}</td>
            <td>${escapeHtml(row.action)}</td>
            <td>${escapeHtml(row.start_date)}</td>
            <td>${escapeHtml(row.end_date)}</td>
            <td>${escapeHtml(row.maker)}</td>
            <td>${escapeHtml(row.checker || "")}</td>
            <td>${escapeHtml(row.pod)}</td>
            <td>${escapeHtml(row.remark)}</td>
            <td>
              <div class="row-actions">
                <button data-approve="${row.id}">Approve</button>
                <button class="reject" data-reject="${row.id}">Reject</button>
              </div>
            </td>
          </tr>
        `
      )
      .join("") || `<tr><td colspan="11">No pending requests.</td></tr>`;
}

async function loadExportPreview() {
  const rows = await api("/api/export-preview");
  state.exportRows = rows;
  renderExportPreview();
}

function setExportFilter(filter) {
  state.exportFilter = filter;
  state.exportPage = 1;
  renderExportPreview();
}

function renderExportPreview() {
  const filteredRows =
    state.exportFilter === "ALL"
      ? state.exportRows
      : state.exportRows.filter((row) => row.action === state.exportFilter);
  const rows = [...filteredRows].sort((a, b) =>
    String(b.created_at || "").localeCompare(String(a.created_at || ""))
  );
  const totalPages = Math.max(1, Math.ceil(rows.length / state.exportPageSize));
  state.exportPage = Math.min(Math.max(1, state.exportPage), totalPages);
  const pageStart = (state.exportPage - 1) * state.exportPageSize;
  const pageRows = rows.slice(pageStart, pageStart + state.exportPageSize);
  const labels = {
    ALL: "Shows the full picture that would be exported now.",
    STOP: "Showing current STOP records that would be exported now.",
    RESUME: "Showing current RESUME records that would be exported now.",
  };
  $("#exportPreviewLabel").textContent = labels[state.exportFilter];
  $("#willExportMetric").classList.toggle("active", state.exportFilter === "ALL");
  $("#currentStopMetric").classList.toggle("active", state.exportFilter === "STOP");
  $("#currentResumeMetric").classList.toggle("active", state.exportFilter === "RESUME");
  $("#exportPageLabel").textContent = `Page ${state.exportPage} of ${totalPages}`;
  $("#exportPrevPage").disabled = state.exportPage <= 1;
  $("#exportNextPage").disabled = state.exportPage >= totalPages;
  $("#exportPreviewBody").innerHTML =
    pageRows
      .map(
        (row) => `
          <tr>
            <td>${row.id}</td>
            <td>${escapeHtml(formatDateTime(row.created_at))}</td>
            <td>${escapeHtml(row.run_num)}</td>
            <td>${escapeHtml(row.action)}</td>
            <td>${badge(row.status)}</td>
            <td>${escapeHtml(row.start_date)}</td>
            <td>${escapeHtml(row.end_date)}</td>
            <td>${escapeHtml(row.checker || "")}</td>
            <td>${escapeHtml(row.approval_date || "")}</td>
            <td>${escapeHtml(row.export_batch_id || "")}</td>
          </tr>
        `
      )
      .join("") || `<tr><td colspan="10">No approved/exported records would be exported.</td></tr>`;
}

function changeExportPage(delta) {
  state.exportPage += delta;
  renderExportPreview();
}

async function refreshAll() {
  await loadSummary();
  await loadPending();
  await loadExportPreview();
}

async function submitRequest(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = $("#formMessage");
  message.textContent = "";
  message.className = "message";

  const payload = Object.fromEntries(new FormData(form));
  try {
    const row = await api("/api/requests", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    message.textContent = `Submitted request #${row.id}.`;
    message.classList.add("ok");
    form.run_num.value = "";
    form.remark.value = "";
    await refreshDateDefaults();
    await refreshAll();
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  }
}

async function decide(id, decision) {
  const checker = $("#checkerFilter").value.trim();
  if (!checker) {
    alert("Filter by checker name is required before approve/reject.");
    return;
  }
  try {
    await api(`/api/requests/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, checker }),
    });
    await refreshAll();
  } catch (error) {
    alert(error.message);
  }
}

async function lookupRunNum() {
  const runNum = $("#lookupRunNum").value.trim();
  if (!runNum) return;
  try {
    const data = await api(`/api/history?run_num=${encodeURIComponent(runNum)}`);
    const statusClass =
      data.current_status === "STOPPED" ? "status-stopped" : "status-resumed";
    const record = data.current_record;
    $("#currentStatus").className = "status-box";
    $("#currentStatus").innerHTML = record
      ? `
        <strong>Current:</strong>
        <span class="${statusClass}">${data.current_status}</span>
        <div>Latest action: ${escapeHtml(record.action)} | End_Date: ${escapeHtml(record.end_date)} | Maker: ${escapeHtml(record.maker)}</div>
        <div>Remark: ${escapeHtml(record.remark)}</div>
      `
      : `<strong>Current:</strong> NO_RECORD`;
    $("#historyBody").innerHTML =
      data.history
        .map(
          (row) => `
            <tr>
              <td>${row.id}</td>
              <td>${escapeHtml(formatDateTime(row.created_at))}</td>
              <td>${escapeHtml(row.action)}</td>
              <td>${badge(row.status)}</td>
              <td>${escapeHtml(row.start_date)}</td>
              <td>${escapeHtml(row.end_date)}</td>
              <td>${escapeHtml(row.maker)}</td>
              <td>${escapeHtml(row.export_batch_id || "")}</td>
              <td>${escapeHtml(row.remark)}</td>
            </tr>
          `
        )
        .join("") || `<tr><td colspan="9">No history.</td></tr>`;
  } catch (error) {
    alert(error.message);
  }
}

async function exportExcel() {
  try {
    const data = await api("/api/export", { method: "POST", body: "{}" });
    const link = $("#exportLink");
    const fileName = data.file.split(/[\\/]/).pop();
    link.hidden = false;
    link.href = `/exports/${fileName}`;
    link.textContent = `Open ${fileName} (${data.record_count} rows)`;
    await refreshAll();
  } catch (error) {
    alert(error.message);
  }
}

async function importHistory(event) {
  event.preventDefault();
  const message = $("#importMessage");
  const fileInput = $("#importFile");
  message.textContent = "";
  message.className = "message";
  if (!fileInput.files.length) {
    message.textContent = "Please choose an Excel file.";
    message.classList.add("error");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  try {
    const response = await fetch("/api/import-history", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(data.error || "Import failed");
    }
    message.textContent = `Imported ${data.imported_count} records. Skipped ${data.skipped_blank_run_num} rows without Run_Num.`;
    message.classList.add("ok");
    fileInput.value = "";
    await refreshAll();
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  }
}

document.addEventListener("change", (event) => {
  if (event.target.name === "action") {
    refreshDateDefaults();
  }
});

document.addEventListener("input", (event) => {
  if (event.target.name === "run_num") {
    refreshDateDefaults();
  }
});

document.addEventListener("click", (event) => {
  const approve = event.target.dataset?.approve;
  const reject = event.target.dataset?.reject;
  if (approve) decide(approve, "approve");
  if (reject) decide(reject, "reject");
});

$("#requestForm").addEventListener("submit", submitRequest);
$("#importForm").addEventListener("submit", importHistory);
$("#refreshButton").addEventListener("click", refreshAll);
$("#lookupButton").addEventListener("click", lookupRunNum);
$("#willExportMetric").addEventListener("click", () => setExportFilter("ALL"));
$("#currentStopMetric").addEventListener("click", () => setExportFilter("STOP"));
$("#currentResumeMetric").addEventListener("click", () => setExportFilter("RESUME"));
$("#exportPrevPage").addEventListener("click", () => changeExportPage(-1));
$("#exportNextPage").addEventListener("click", () => changeExportPage(1));
$("#pendingMetric").addEventListener("click", () => {
  document.querySelector("#pendingBody").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("#checkerFilter").addEventListener("input", loadPending);
$("#podFilter").addEventListener("input", loadPending);
$("#clearCheckerFilter").addEventListener("click", () => {
  $("#checkerFilter").value = "";
  $("#podFilter").value = "";
  loadPending();
});
$("#lookupRunNum").addEventListener("keydown", (event) => {
  if (event.key === "Enter") lookupRunNum();
});
$("#exportButton").addEventListener("click", exportExcel);

refreshAll();
