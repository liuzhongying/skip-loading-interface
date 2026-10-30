const state = {
  today: "",
  exportRows: [],
  exportFilter: "ALL",
  exportPage: 1,
  exportPageSize: 10,
  exportTotalPages: 1,
  activeDagId: "",
  dagPage: 1,
  dagTotalPages: 1,
  dagHistoryPage: 1,
  dagHistoryTotalPages: 1,
  activeTaskKey: "",
  taskPage: 1,
  taskTotalPages: 1,
  taskHistoryPage: 1,
  taskHistoryTotalPages: 1,
};

const $ = (selector) => document.querySelector(selector);

const TASK_FIELDS = [
  "dag_id",
  "task_id",
  "task_name",
  "shell_command",
  "dataproc_bucket",
  "main_file_run_on_dataproc",
  "main_python_args",
  "dependency_task",
  "file_wait_bucket",
  "file_wait",
  "filewait_time_out_in_seconds",
  "sensor_task_name",
  "parent_dag",
  "parent_task",
  "marker_task_name",
  "child_dag",
  "child_task_id",
  "task_inactive_flag",
  "trigger_rule",
  "task_unique_key",
  "monthly_start_day",
  "monthly_end_day",
  "weekly_start_day",
  "weekly_end_day",
];

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

function calculatedTaskUniqueKey(dagId, taskId) {
  const left = String(dagId || "").trim();
  const right = String(taskId || "").trim();
  return left || right ? `${left}||${right}` : "";
}

function refreshTaskUniqueKey() {
  const form = $("#taskForm");
  if (!form.task_unique_key.value.trim()) {
    form.task_unique_key.value = calculatedTaskUniqueKey(form.dag_id.value, form.task_id.value);
  }
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

async function loadDagEntries() {
  const dagId = $("#dagFilter").value.trim();
  const query = new URLSearchParams();
  if (dagId) query.set("dag_id", dagId);
  query.set("page", state.dagPage);
  const rows = await api(`/api/dag-entries?${query.toString()}`);
  state.dagPage = rows.page || 1;
  state.dagTotalPages = rows.total_pages || 1;
  $("#dagPageLabel").textContent = `Page ${state.dagPage} of ${state.dagTotalPages} (${rows.total || 0} DAGs)`;
  $("#dagPageInput").value = state.dagPage;
  $("#dagPageInput").max = state.dagTotalPages;
  $("#dagPrevPage").disabled = state.dagPage <= 1;
  $("#dagNextPage").disabled = state.dagPage >= state.dagTotalPages;
  $("#dagBody").innerHTML =
    rows.rows
      .map(
        (row) => `
          <tr>
            <td>${row.id}</td>
            <td>${escapeHtml(formatDateTime(row.created_at))}</td>
            <td>${escapeHtml(row.dag_id)}</td>
            <td>${escapeHtml(row.description)}</td>
            <td>${escapeHtml(row.schedule_interval)}</td>
            <td>${escapeHtml(row.start_datetime)}</td>
            <td>${escapeHtml(row.end_date)}</td>
            <td>${escapeHtml(row.status)}</td>
            <td>${escapeHtml(row.owner)}</td>
            <td>${escapeHtml(row.request_type)}</td>
            <td>${escapeHtml(row.run_on_holiday)}</td>
          </tr>
        `
      )
      .join("") || `<tr><td colspan="11">No DAG records.</td></tr>`;
}

function fillDagForm(row) {
  const form = $("#dagForm");
  [
    "dag_id",
    "description",
    "schedule_interval",
    "event_date_table",
    "start_datetime",
    "end_date",
    "status",
    "email",
    "owner",
    "last_released_date",
    "gcp_project_id",
    "ad_group",
    "machine_type",
    "mount_bucket",
    "image_version",
    "request_type",
    "num_workers",
    "bucket_folder",
    "run_on_holiday",
    "vm_alive_days",
    "skip_run_base_completion_token",
    "token_file_bucket",
    "token_file_path_in_bucket",
    "token_file_offset",
    "pega_night_batch_flag",
    "stop_successful_mail_ser",
    "pega_intra_batch_flag",
    "myfeed_reminder_flag",
  ].forEach((key) => {
    if (form.elements[key]) {
      form.elements[key].value = row?.[key] ?? "";
    }
  });
}

function renderDagHistory(data) {
  const rows = data.history || [];
  state.dagHistoryPage = data.page || 1;
  state.dagHistoryTotalPages = data.total_pages || 1;
  $("#dagHistoryLabel").textContent = rows.length
    ? `${data.dag_id}: ${data.total || 0} version(s), newest first.`
    : `${data.dag_id}: no history found.`;
  $("#dagHistoryPageLabel").textContent = `Page ${state.dagHistoryPage} of ${state.dagHistoryTotalPages}`;
  $("#dagHistoryPageInput").value = state.dagHistoryPage;
  $("#dagHistoryPageInput").max = state.dagHistoryTotalPages;
  $("#dagHistoryPrevPage").disabled = state.dagHistoryPage <= 1;
  $("#dagHistoryNextPage").disabled = state.dagHistoryPage >= state.dagHistoryTotalPages;
  $("#dagHistoryBody").innerHTML =
    rows
      .map(
        (row) => `
          <tr>
            <td>${row.id}</td>
            <td>${escapeHtml(formatDateTime(row.created_at))}</td>
            <td>${escapeHtml(row.previous_entry_id || "")}</td>
            <td>${escapeHtml(row.dag_id)}</td>
            <td>${escapeHtml(row.description)}</td>
            <td>${escapeHtml(row.schedule_interval)}</td>
            <td>${escapeHtml(row.start_datetime)}</td>
            <td>${escapeHtml(row.end_date)}</td>
            <td>${escapeHtml(row.status)}</td>
            <td>${escapeHtml(row.owner)}</td>
            <td>${escapeHtml(row.request_type)}</td>
            <td>${escapeHtml(row.run_on_holiday)}</td>
            <td>${formatDagChanges(row.changes)}</td>
          </tr>
        `
      )
      .join("") || `<tr><td colspan="13">No history for this dag_id.</td></tr>`;
}

function formatDagChanges(changes) {
  if (!changes || !changes.length) {
    return `<span class="muted-text">No field changes</span>`;
  }
  return `
    <ul class="change-list">
      ${changes
        .map(
          (change) => `
            <li>
              <strong>${escapeHtml(change.label || change.field)}</strong>:
              <span>${escapeHtml(change.old || "(blank)")}</span>
              <span class="change-arrow">to</span>
              <span>${escapeHtml(change.new || "(blank)")}</span>
            </li>
          `
        )
        .join("")}
    </ul>
  `;
}

async function loadDagForEdit() {
  const dagId = $("#dagLookupId").value.trim();
  if (!dagId) {
    clearDagHistory();
    return;
  }
  try {
    const query = new URLSearchParams({ dag_id: dagId, page: state.dagHistoryPage });
    const data = await api(`/api/dag-history?${query.toString()}`);
    state.activeDagId = data.dag_id;
    if (data.current_record) {
      fillDagForm(data.current_record);
      $("#dagMessage").textContent = `Loaded latest version #${data.current_record.id}.`;
      $("#dagMessage").className = "message ok";
    } else {
      $("#dagMessage").textContent = "No existing DAG record. You can create a new one.";
      $("#dagMessage").className = "message";
    }
    renderDagHistory(data);
  } catch (error) {
    $("#dagMessage").textContent = error.message;
    $("#dagMessage").className = "message error";
  }
}

function clearDagHistory() {
  state.activeDagId = "";
  state.dagHistoryPage = 1;
  state.dagHistoryTotalPages = 1;
  $("#dagHistoryLabel").textContent = "No dag_id loaded.";
  $("#dagHistoryBody").innerHTML = `<tr><td colspan="13">No history loaded.</td></tr>`;
  $("#dagHistoryPageLabel").textContent = "Page 1 of 1";
  $("#dagHistoryPageInput").value = 1;
  $("#dagHistoryPageInput").max = 1;
  $("#dagHistoryPrevPage").disabled = true;
  $("#dagHistoryNextPage").disabled = true;
}

function setDagPage(page) {
  state.dagPage = Math.min(Math.max(1, page), state.dagTotalPages);
  loadDagEntries();
}

function setDagHistoryPage(page) {
  if (!state.activeDagId) {
    clearDagHistory();
    return;
  }
  state.dagHistoryPage = Math.min(Math.max(1, page), state.dagHistoryTotalPages);
  loadDagForEdit();
}

async function loadTaskEntries() {
  const taskKey = $("#taskFilter").value.trim();
  const query = new URLSearchParams();
  if (taskKey) query.set("task_id", taskKey);
  query.set("page", state.taskPage);
  const rows = await api(`/api/task-entries?${query.toString()}`);
  state.taskPage = rows.page || 1;
  state.taskTotalPages = rows.total_pages || 1;
  $("#taskPageLabel").textContent = `Page ${state.taskPage} of ${state.taskTotalPages} (${rows.total || 0} TASKS)`;
  $("#taskPageInput").value = state.taskPage;
  $("#taskPageInput").max = state.taskTotalPages;
  $("#taskPrevPage").disabled = state.taskPage <= 1;
  $("#taskNextPage").disabled = state.taskPage >= state.taskTotalPages;
  $("#taskBody").innerHTML =
    rows.rows
      .map(
        (row) => `
          <tr>
            <td>${row.id}</td>
            <td>${escapeHtml(formatDateTime(row.created_at))}</td>
            <td>${escapeHtml(row.dag_id)}</td>
            <td>${escapeHtml(row.task_id)}</td>
            <td>${escapeHtml(row.task_unique_key)}</td>
            <td>${escapeHtml(row.task_name)}</td>
            <td>${escapeHtml(row.shell_command)}</td>
            <td>${escapeHtml(row.dependency_task || "")}</td>
            <td>${escapeHtml(row.trigger_rule || "")}</td>
          </tr>
        `
      )
      .join("") || `<tr><td colspan="9">No TASKS records.</td></tr>`;
}

function fillTaskForm(row) {
  const form = $("#taskForm");
  TASK_FIELDS.forEach((key) => {
    if (form.elements[key]) {
      form.elements[key].value = row?.[key] ?? "";
    }
  });
}

function clearTaskHistory() {
  state.activeTaskKey = "";
  state.taskHistoryPage = 1;
  state.taskHistoryTotalPages = 1;
  $("#taskHistoryLabel").textContent = "No task_id loaded.";
  $("#taskHistoryBody").innerHTML = `<tr><td colspan="10">No history loaded.</td></tr>`;
  $("#taskHistoryPageLabel").textContent = "Page 1 of 1";
  $("#taskHistoryPageInput").value = 1;
  $("#taskHistoryPageInput").max = 1;
  $("#taskHistoryPrevPage").disabled = true;
  $("#taskHistoryNextPage").disabled = true;
}

function renderTaskHistory(data) {
  const rows = data.history || [];
  state.taskHistoryPage = data.page || 1;
  state.taskHistoryTotalPages = data.total_pages || 1;
  $("#taskHistoryLabel").textContent = rows.length
    ? `${data.task_id}: ${data.total || 0} version(s), newest first.`
    : `${data.task_id}: no history found.`;
  $("#taskHistoryPageLabel").textContent = `Page ${state.taskHistoryPage} of ${state.taskHistoryTotalPages}`;
  $("#taskHistoryPageInput").value = state.taskHistoryPage;
  $("#taskHistoryPageInput").max = state.taskHistoryTotalPages;
  $("#taskHistoryPrevPage").disabled = state.taskHistoryPage <= 1;
  $("#taskHistoryNextPage").disabled = state.taskHistoryPage >= state.taskHistoryTotalPages;
  $("#taskHistoryBody").innerHTML =
    rows
      .map(
        (row) => `
          <tr>
            <td>${row.id}</td>
            <td>${escapeHtml(formatDateTime(row.created_at))}</td>
            <td>${escapeHtml(row.previous_entry_id || "")}</td>
            <td>${escapeHtml(row.dag_id)}</td>
            <td>${escapeHtml(row.task_id)}</td>
            <td>${escapeHtml(row.task_unique_key)}</td>
            <td>${escapeHtml(row.task_name)}</td>
            <td>${escapeHtml(row.trigger_rule || "")}</td>
            <td>${escapeHtml(row.task_inactive_flag || "")}</td>
            <td>${formatDagChanges(row.changes)}</td>
          </tr>
        `
      )
      .join("") || `<tr><td colspan="10">No history for this task_id.</td></tr>`;
}

async function loadTaskForEdit() {
  const taskKey = $("#taskLookupKey").value.trim();
  if (!taskKey) {
    clearTaskHistory();
    return;
  }
  try {
    const query = new URLSearchParams({ task_id: taskKey, page: state.taskHistoryPage });
    const data = await api(`/api/task-history?${query.toString()}`);
    state.activeTaskKey = data.task_id;
    if (data.current_record) {
      fillTaskForm(data.current_record);
      $("#taskMessage").textContent = `Loaded latest version #${data.current_record.id}.`;
      $("#taskMessage").className = "message ok";
    } else {
      $("#taskMessage").textContent = "No existing TASKS record. You can create a new one.";
      $("#taskMessage").className = "message";
    }
    renderTaskHistory(data);
  } catch (error) {
    $("#taskMessage").textContent = error.message;
    $("#taskMessage").className = "message error";
  }
}

function setTaskPage(page) {
  state.taskPage = Math.min(Math.max(1, page), state.taskTotalPages);
  loadTaskEntries();
}

function setTaskHistoryPage(page) {
  if (!state.activeTaskKey) {
    clearTaskHistory();
    return;
  }
  state.taskHistoryPage = Math.min(Math.max(1, page), state.taskHistoryTotalPages);
  loadTaskForEdit();
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
    String(b.created_at || "").localeCompare(String(a.created_at || "")) ||
    Number(b.id || 0) - Number(a.id || 0)
  );
  const totalPages = Math.max(1, Math.ceil(rows.length / state.exportPageSize));
  state.exportTotalPages = totalPages;
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
  $("#exportPageInput").value = state.exportPage;
  $("#exportPageInput").max = totalPages;
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

function setExportPage(page) {
  state.exportPage = Math.min(Math.max(1, page), state.exportTotalPages);
  renderExportPreview();
}

async function refreshAll() {
  await loadSummary();
  await loadPending();
  await loadExportPreview();
  await loadDagEntries();
  await loadTaskEntries();
}

async function submitRequest(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = $("#formMessage");
  message.textContent = "";
  message.className = "message";

  const payload = Object.fromEntries(new FormData(form));
  if (!String(payload.task_unique_key || "").trim()) {
    payload.task_unique_key = calculatedTaskUniqueKey(payload.dag_id, payload.task_id);
  }
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

async function importDagExcel(event) {
  event.preventDefault();
  const message = $("#dagImportMessage");
  const fileInput = $("#dagImportFile");
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
    const response = await fetch("/api/dag-import", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(data.error || "Import failed");
    }
    const failedText = data.failed_count
      ? ` Failed ${data.failed_count} row(s); first issue: row ${data.failed_rows[0].row} - ${data.failed_rows[0].error}.`
      : "";
    message.textContent =
      `Imported ${data.imported_count} DAG record(s) from ${data.sheet}. ` +
      `Skipped ${data.skipped_unchanged} unchanged and ${data.skipped_blank_dag_id} blank dag_id row(s).` +
      failedText;
    message.classList.add(data.failed_count ? "error" : "ok");
    fileInput.value = "";
    state.dagPage = 1;
    await loadDagEntries();
    if (state.activeDagId) {
      state.dagHistoryPage = 1;
      $("#dagLookupId").value = state.activeDagId;
      await loadDagForEdit();
    }
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  }
}

async function submitDagEntry(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = $("#dagMessage");
  message.textContent = "";
  message.className = "message";

  const payload = Object.fromEntries(new FormData(form));
  try {
    const row = await api("/api/dag-entries", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    message.textContent = `Saved DAG row #${row.id}.`;
    message.classList.add("ok");
    state.activeDagId = row.dag_id;
    $("#dagLookupId").value = row.dag_id;
    state.dagHistoryPage = 1;
    form.dag_id.value = "";
    form.description.value = "";
    form.schedule_interval.value = "";
    form.event_date_table.value = "";
    form.start_datetime.value = "";
    form.end_date.value = "";
    form.email.value = "";
    form.owner.value = "";
    form.last_released_date.value = "";
    form.machine_type.value = "";
    form.image_version.value = "";
    form.request_type.value = "";
    form.num_workers.value = "";
    form.run_on_holiday.value = "";
    form.vm_alive_days.value = "";
    form.skip_run_base_completion_token.value = "";
    form.token_file_bucket.value = "";
    form.token_file_path_in_bucket.value = "";
    form.pega_night_batch_flag.value = "";
    form.stop_successful_mail_ser.value = "";
    form.pega_intra_batch_flag.value = "";
    form.myfeed_reminder_flag.value = "";
    await loadDagEntries();
    await loadDagForEdit();
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  }
}

async function exportDagExcel() {
  try {
    const data = await api("/api/dag-export", { method: "POST", body: "{}" });
    const link = $("#dagExportLink");
    const fileName = data.file.split(/[\\/]/).pop();
    link.hidden = false;
    link.href = `/exports/${fileName}`;
    link.textContent = `Open ${fileName} (${data.record_count} rows)`;
  } catch (error) {
    alert(error.message);
  }
}

async function importTasksExcel(event) {
  event.preventDefault();
  const message = $("#tasksImportMessage");
  const fileInput = $("#tasksImportFile");
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
    const response = await fetch("/api/tasks-import", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok || data.error) {
      throw new Error(data.error || "Import failed");
    }
    const failedText = data.failed_count
      ? ` Failed ${data.failed_count} row(s); first issue: row ${data.failed_rows[0].row} - ${data.failed_rows[0].error}.`
      : "";
    message.textContent =
      `Imported ${data.imported_count} TASKS record(s) from ${data.sheet}. ` +
      `Skipped ${data.skipped_unchanged} unchanged and ${data.skipped_blank_task} blank task row(s).` +
      failedText;
    message.classList.add(data.failed_count ? "error" : "ok");
    fileInput.value = "";
    state.taskPage = 1;
    await loadTaskEntries();
    if (state.activeTaskKey) {
      state.taskHistoryPage = 1;
      $("#taskLookupKey").value = state.activeTaskKey;
      await loadTaskForEdit();
    }
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  }
}

async function submitTaskEntry(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = $("#taskMessage");
  message.textContent = "";
  message.className = "message";

  const payload = Object.fromEntries(new FormData(form));
  try {
    const row = await api("/api/task-entries", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    message.textContent = `Saved TASKS row #${row.id}.`;
    message.classList.add("ok");
    state.activeTaskKey = row.task_id;
    $("#taskLookupKey").value = row.task_id;
    state.taskHistoryPage = 1;
    form.reset();
    form.file_wait_bucket.value = "hsbc-10272718-ombbusvis-prod-team-wpbcamp";
    form.filewait_time_out_in_seconds.value = "0";
    await loadTaskEntries();
    await loadTaskForEdit();
  } catch (error) {
    message.textContent = error.message;
    message.classList.add("error");
  }
}

async function exportTasksExcel() {
  try {
    const data = await api("/api/tasks-export", { method: "POST", body: "{}" });
    const link = $("#tasksExportLink");
    const fileName = data.file.split(/[\\/]/).pop();
    link.hidden = false;
    link.href = `/exports/${fileName}`;
    link.textContent = `Open ${fileName} (${data.record_count} rows)`;
  } catch (error) {
    alert(error.message);
  }
}

async function exportDatabaseJson() {
  try {
    const data = await api("/api/export-json", { method: "POST", body: "{}" });
    const link = $("#exportJsonLink");
    const fileName = data.file.split(/[\\/]/).pop();
    link.hidden = false;
    link.href = `/exports/${fileName}`;
    link.textContent =
      `Open ${fileName} (` +
      `${data.run_num_count || 0} Run_Num, ` +
      `${data.task_only_run_num_count || 0} task-only Run_Num, ` +
      `${data.matched_task_count || 0} matched TASKS)`;
  } catch (error) {
    alert(error.message);
  }
}

function showPage(pageId) {
  document.querySelectorAll(".page").forEach((page) => {
    const active = page.id === pageId;
    page.hidden = !active;
    page.classList.toggle("active", active);
  });
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.page === pageId);
  });
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
  if (event.target.form?.id === "taskForm" && ["dag_id", "task_id"].includes(event.target.name)) {
    refreshTaskUniqueKey();
  }
  if (event.target.form?.id === "taskForm" && event.target.name === "task_unique_key") {
    refreshTaskUniqueKey();
  }
});

document.addEventListener("click", (event) => {
  const approve = event.target.dataset?.approve;
  const reject = event.target.dataset?.reject;
  if (approve) decide(approve, "approve");
  if (reject) decide(reject, "reject");
});

$("#requestForm").addEventListener("submit", submitRequest);
$("#dagForm").addEventListener("submit", submitDagEntry);
$("#taskForm").addEventListener("submit", submitTaskEntry);
$("#importForm").addEventListener("submit", importHistory);
$("#dagImportForm").addEventListener("submit", importDagExcel);
$("#tasksImportForm").addEventListener("submit", importTasksExcel);
let mcPage = 1;
let mcTotalPages = 1;
let mcActiveKey = "";
async function loadMcPage(page) {
  if (!mcActiveKey) return;
  try {
    const result = await api(`/api/mc?key=${encodeURIComponent(mcActiveKey)}&page=${page}`);
    mcPage = result.page;
    mcTotalPages = result.total_pages;
    $("#mcBody").innerHTML = result.items.map((row) => `<tr>${["proposition_active", "py_name", "py_label", "bs_group", "prod_start_dt", "eligibility_rule", "start_date", "end_date"].map((field) => `<td>${escapeHtml(row[field])}</td>`).join("")}</tr>`).join("") || '<tr><td colspan="8">No matching records.</td></tr>';
    $("#mcMessage").textContent = `${result.total} record(s) found.`;
    $("#mcPageLabel").textContent = `Page ${mcPage} of ${mcTotalPages}`;
    $("#mcPrev").disabled = mcPage <= 1;
    $("#mcNext").disabled = mcPage >= mcTotalPages;
  } catch (error) {
    $("#mcMessage").textContent = error.message;
  }
}
$("#mcLookupForm").addEventListener("submit", (event) => {
  event.preventDefault();
  mcActiveKey = $("#mcKey").value.trim();
  if (mcActiveKey) loadMcPage(1);
});
$("#mcPrev").addEventListener("click", () => loadMcPage(mcPage - 1));
$("#mcNext").addEventListener("click", () => loadMcPage(mcPage + 1));
$("#mcImportForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("#mcImportMessage");
  const button = event.currentTarget.querySelector("button");
  const data = new FormData(event.currentTarget);
  button.disabled = true;
  message.textContent = "Importing...";
  try {
    const response = await fetch("/api/mc-import", { method: "POST", body: data });
    const result = await response.json();
    if (!response.ok || result.error) throw new Error(result.error || "Import failed");
    message.textContent = `Imported ${result.imported_count} record(s) from ${result.sheet}; skipped ${result.skipped_count} row(s) without pyName.`;
    if (!result.bs_group_found) message.textContent += " BSGroup column not found; values are blank.";
    event.target.reset();
    if (mcActiveKey) await loadMcPage(1);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#refreshButton").addEventListener("click", refreshAll);
let runningResult = null;
$("#runningForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  runningResult = null;
  $("#runningDownload").disabled = true;
  $("#runningExcelDownload").disabled = true;
  $("#runningResults").replaceChildren();
  $("#runningMessage").textContent = "Checking…";
  const pyNames = $("#runningInput").value.split(/[\n,，;；]+/).map((name) => name.trim()).filter(Boolean);
  try {
    const data = await api("/api/running-status", {
      method: "POST", body: JSON.stringify({ py_names: pyNames }),
    });
    runningResult = data;
    $("#runningDownload").disabled = false;
    $("#runningExcelDownload").disabled = false;
    $("#runningMessage").textContent = `Checked ${data.results.length} pyName(s), as of ${data.today}.`;
    $("#runningResults").innerHTML = data.results.map((item) => `
      <article class="panel">
        <h3>${escapeHtml(item.py_name)} — ${escapeHtml(item.status)}</h3>
        <p>${escapeHtml(item.reason)}</p>
        ${item.tasks.length ? `<ul>${item.tasks.map((task) => `<li><strong>${escapeHtml(task.task_id)}</strong> (${escapeHtml(task.dag_id)}): ${escapeHtml(task.status)} — ${escapeHtml(task.reason)}</li>`).join("")}</ul>` : ""}
        ${item.mc_entries.length ? `<ul>${item.mc_entries.map((mc) => `<li><strong>MC record ${escapeHtml(mc.id)}</strong>: ${escapeHtml(mc.combined_status ?? mc.status)} (MC: ${escapeHtml(mc.status)}) — ${escapeHtml(mc.reason)}</li>`).join("")}</ul>` : ""}
      </article>`).join("");
  } catch (error) {
    $("#runningMessage").textContent = error.message;
  }
});
$("#runningDownload").addEventListener("click", () => {
  if (!runningResult) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(runningResult, null, 2)], {type: "application/json"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = `running-status-${runningResult.today}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("#runningExcelDownload").addEventListener("click", async () => {
  if (!runningResult) return;
  const button = $("#runningExcelDownload");
  button.disabled = true;
  try {
    const response = await fetch("/api/running-status-excel", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(runningResult),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "Excel export failed");
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `running-status-${runningResult.today}.xlsx`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    $("#runningMessage").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#exportJsonButton").addEventListener("click", exportDatabaseJson);
$("#lookupButton").addEventListener("click", lookupRunNum);
$("#dagLookupButton").addEventListener("click", loadDagForEdit);
$("#taskLookupButton").addEventListener("click", loadTaskForEdit);
$("#willExportMetric").addEventListener("click", () => setExportFilter("ALL"));
$("#currentStopMetric").addEventListener("click", () => setExportFilter("STOP"));
$("#currentResumeMetric").addEventListener("click", () => setExportFilter("RESUME"));
$("#exportPrevPage").addEventListener("click", () => changeExportPage(-1));
$("#exportNextPage").addEventListener("click", () => changeExportPage(1));
$("#exportGoPage").addEventListener("click", () => setExportPage(Number($("#exportPageInput").value || 1)));
$("#exportPageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") setExportPage(Number($("#exportPageInput").value || 1));
});
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
$("#dagFilter").addEventListener("input", () => {
  state.dagPage = 1;
  loadDagEntries();
});
$("#dagExportButton").addEventListener("click", exportDagExcel);
$("#taskFilter").addEventListener("input", () => {
  state.taskPage = 1;
  loadTaskEntries();
});
$("#tasksExportButton").addEventListener("click", exportTasksExcel);
$("#clearDagForm").addEventListener("click", () => {
  $("#dagForm").reset();
  $("#dagLookupId").value = "";
  clearDagHistory();
  $("#dagMessage").textContent = "";
  $("#dagMessage").className = "message";
});
$("#clearTaskForm").addEventListener("click", () => {
  $("#taskForm").reset();
  $("#taskForm").file_wait_bucket.value = "hsbc-10272718-ombbusvis-prod-team-wpbcamp";
  $("#taskForm").filewait_time_out_in_seconds.value = "0";
  refreshTaskUniqueKey();
  $("#taskLookupKey").value = "";
  clearTaskHistory();
  $("#taskMessage").textContent = "";
  $("#taskMessage").className = "message";
});
$("#dagLookupId").addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadDagForEdit();
});
$("#taskLookupKey").addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadTaskForEdit();
});
document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => showPage(button.dataset.page));
});
$("#dagPrevPage").addEventListener("click", () => setDagPage(state.dagPage - 1));
$("#dagNextPage").addEventListener("click", () => setDagPage(state.dagPage + 1));
$("#dagGoPage").addEventListener("click", () => setDagPage(Number($("#dagPageInput").value || 1)));
$("#dagPageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") setDagPage(Number($("#dagPageInput").value || 1));
});
$("#dagHistoryPrevPage").addEventListener("click", () => setDagHistoryPage(state.dagHistoryPage - 1));
$("#dagHistoryNextPage").addEventListener("click", () => setDagHistoryPage(state.dagHistoryPage + 1));
$("#dagHistoryGoPage").addEventListener("click", () => setDagHistoryPage(Number($("#dagHistoryPageInput").value || 1)));
$("#dagHistoryPageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") setDagHistoryPage(Number($("#dagHistoryPageInput").value || 1));
});
$("#taskPrevPage").addEventListener("click", () => setTaskPage(state.taskPage - 1));
$("#taskNextPage").addEventListener("click", () => setTaskPage(state.taskPage + 1));
$("#taskGoPage").addEventListener("click", () => setTaskPage(Number($("#taskPageInput").value || 1)));
$("#taskPageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") setTaskPage(Number($("#taskPageInput").value || 1));
});
$("#taskHistoryPrevPage").addEventListener("click", () => setTaskHistoryPage(state.taskHistoryPage - 1));
$("#taskHistoryNextPage").addEventListener("click", () => setTaskHistoryPage(state.taskHistoryPage + 1));
$("#taskHistoryGoPage").addEventListener("click", () => setTaskHistoryPage(Number($("#taskHistoryPageInput").value || 1)));
$("#taskHistoryPageInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") setTaskHistoryPage(Number($("#taskHistoryPageInput").value || 1));
});

refreshAll();

