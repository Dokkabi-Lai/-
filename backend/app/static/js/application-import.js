var APPLICATION_IMPORT_COLUMNS = [
  { key: "company", label: "公司名称", width: 230 },
  { key: "title", label: "岗位名称", width: 250 },
  { key: "applied_at", label: "投递时间", width: 190 }
];

var APPLICATION_IMPORT_ALIASES = {
  "公司": "company", "公司名称": "company", "公司名字": "company", "企业": "company", "company": "company",
  "岗位": "title", "岗位名称": "title", "投递岗位": "title", "职位": "title", "职位名称": "title", "title": "title",
  "投递时间": "applied_at", "投递日期": "applied_at", "日期": "applied_at", "appliedat": "applied_at"
};

var _applicationImportRows = [];
var _applicationImportActive = { row: 0, col: 0 };
var _applicationImportSubmitting = false;

function emptyApplicationImportRow() {
  return { company: "", title: "", applied_at: "", _error: "" };
}

function openApplicationImport() {
  _applicationImportRows = [];
  while (_applicationImportRows.length < 5) _applicationImportRows.push(emptyApplicationImportRow());
  _applicationImportActive = { row: 0, col: 0 };

  var overlay = el("div", { class: "job-grid-overlay", id: "application-import-overlay" },
    el("div", { class: "job-grid-shell application-import-shell" },
      el("header", { class: "job-grid-header" },
        el("div", {},
          el("div", { class: "eyebrow" }, "APPLICATION IMPORT"),
          el("h2", {}, "批量导入投递记录"),
          el("p", { class: "muted" }, "上传 Excel / CSV，或直接从表格复制粘贴；重复记录会自动跳过")
        ),
        el("div", { class: "job-grid-header-actions" },
          el("button", { class: "btn", onclick: chooseApplicationImportFile }, "上传表格"),
          el("button", { class: "btn", onclick: pasteApplicationImportFromClipboard }, "从剪贴板粘贴"),
          el("button", { class: "btn", onclick: downloadApplicationImportTemplate }, "下载模板"),
          el("button", { class: "btn", onclick: addApplicationImportRow }, "+ 添加行"),
          el("button", { class: "btn primary", id: "application-import-submit", onclick: submitApplicationImport }, "确认导入"),
          el("button", { class: "icon-btn grid-close", onclick: closeApplicationImport, title: "关闭", "aria-label": "关闭批量导入" }, "×")
        )
      ),
      el("div", { class: "job-grid-tip application-import-tip" },
        el("span", {}, "必填：公司名称、岗位名称、投递时间"),
        el("span", { id: "application-import-summary" }, "当前 0 条待导入")
      ),
      el("div", { class: "job-grid-scroll", id: "application-import-scroll" })
    )
  );
  document.body.appendChild(overlay);
  renderApplicationImportGrid();
}

function closeApplicationImport() {
  if (_applicationImportSubmitting) return;
  var overlay = document.getElementById("application-import-overlay");
  if (overlay) overlay.remove();
}

function renderApplicationImportGrid() {
  var scroll = document.getElementById("application-import-scroll");
  if (!scroll) return;
  scroll.innerHTML = "";
  var table = el("table", { class: "job-grid-table application-import-table" });
  var head = el("thead", {}, el("tr", {},
    el("th", { class: "row-number" }, "#"),
    ...APPLICATION_IMPORT_COLUMNS.map(function(column) {
      return el("th", { style: "min-width:" + column.width + "px" },
        column.label, el("span", { class: "required-star" }, " *")
      );
    }),
    el("th", { class: "application-import-status-col" }, "校验"),
    el("th", { class: "row-actions-col" }, "")
  ));
  var body = el("tbody");

  _applicationImportRows.forEach(function(row, rowIndex) {
    var tr = el("tr", { class: "job-grid-row" },
      el("td", { class: "row-number" }, rowIndex + 1)
    );
    APPLICATION_IMPORT_COLUMNS.forEach(function(column, colIndex) {
      var input = el("input", {
        value: row[column.key] || "",
        placeholder: column.key === "applied_at" ? "如 2026-10-10 或 2026-10-10 14:30" : "",
        inputmode: column.key === "applied_at" ? "numeric" : null,
        autocomplete: "off"
      });
      input.setAttribute("aria-label", column.label);
      input.onfocus = function() { _applicationImportActive = { row: rowIndex, col: colIndex }; };
      input.oninput = function() {
        row[column.key] = this.value;
        row._error = "";
        this.closest("td").classList.remove("invalid");
        renderApplicationImportStatus(tr, row);
        updateApplicationImportSummary();
      };
      input.onkeydown = function(event) {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          focusApplicationImportCell(rowIndex + 1, colIndex);
        }
      };
      tr.appendChild(el("td", { "data-label": column.label }, input));
    });
    tr.appendChild(el("td", { class: "application-import-status-col", "data-label": "校验" }));
    tr.appendChild(el("td", { class: "row-actions-col" },
      el("button", {
        class: "icon-btn", title: "删除此行", "aria-label": "删除第 " + (rowIndex + 1) + " 行",
        onclick: function() { removeApplicationImportRow(rowIndex); }
      }, "×")
    ));
    renderApplicationImportStatus(tr, row);
    body.appendChild(tr);
  });

  table.appendChild(head);
  table.appendChild(body);
  table.addEventListener("paste", onApplicationImportPaste);
  scroll.appendChild(table);
  updateApplicationImportSummary();
}

function renderApplicationImportStatus(tr, row) {
  var cell = tr.querySelector(".application-import-status-col");
  if (!cell) return;
  cell.innerHTML = "";
  var hasContent = applicationImportRowHasContent(row);
  if (row._error) {
    cell.appendChild(el("span", { class: "application-import-status error", title: row._error }, "需修正"));
  } else if (hasContent) {
    cell.appendChild(el("span", { class: "application-import-status ready" }, "待导入"));
  } else {
    cell.appendChild(el("span", { class: "application-import-status empty" }, "空白"));
  }
}

function applicationImportRowHasContent(row) {
  return APPLICATION_IMPORT_COLUMNS.some(function(column) {
    return String(row[column.key] || "").trim();
  });
}

function addApplicationImportRow() {
  _applicationImportRows.push(emptyApplicationImportRow());
  renderApplicationImportGrid();
  focusApplicationImportCell(_applicationImportRows.length - 1, 0);
}

function removeApplicationImportRow(index) {
  _applicationImportRows.splice(index, 1);
  if (!_applicationImportRows.length) _applicationImportRows.push(emptyApplicationImportRow());
  renderApplicationImportGrid();
}

function focusApplicationImportCell(row, col) {
  if (row >= _applicationImportRows.length) {
    _applicationImportRows.push(emptyApplicationImportRow());
    renderApplicationImportGrid();
  }
  var tr = document.querySelectorAll(".application-import-table tbody tr")[row];
  var cell = tr && tr.querySelectorAll("td")[col + 1];
  var input = cell && cell.querySelector("input");
  if (input) input.focus();
}

function normalizeApplicationImportHeader(value) {
  return String(value || "").toLowerCase().replace(/[\s_]+/g, "");
}

function isApplicationImportSeparatorRow(values) {
  return values.length > 0 && values.every(function(value) {
    return /^:?-{2,}:?$/.test(String(value || "").trim().replace(/\s+/g, ""));
  });
}

function parseApplicationImportClipboard(text) {
  var lines = String(text || "").split(/\r?\n/).map(function(line) {
    return line.trim();
  }).filter(Boolean);
  var pipeLines = lines.filter(function(line) { return line.includes("|"); });
  var looksLikeMarkdownTable = pipeLines.length >= 2 && pipeLines.length >= Math.ceil(lines.length * 0.6);
  if (!looksLikeMarkdownTable) return parseClipboardTable(text);

  return pipeLines.map(function(line) {
    if (line.startsWith("|")) line = line.slice(1);
    if (line.endsWith("|")) line = line.slice(0, -1);
    return line.split("|").map(function(value) { return value.trim(); });
  }).filter(function(values) {
    return values.some(Boolean) && !isApplicationImportSeparatorRow(values);
  });
}

function applyClipboardToApplicationImport(text) {
  var pasted = parseApplicationImportClipboard(text);
  if (!pasted.length) return;
  var mappedKeys = pasted[0].map(function(value) {
    return APPLICATION_IMPORT_ALIASES[normalizeApplicationImportHeader(value)] || null;
  });
  var hasHeader = mappedKeys.includes("company") && mappedKeys.includes("title");
  if (hasHeader) pasted.shift();
  var startRow = hasHeader ? 0 : (_applicationImportActive.row || 0);
  var startCol = hasHeader ? 0 : (_applicationImportActive.col || 0);

  pasted.slice(0, 1000).forEach(function(values, rowOffset) {
    var rowIndex = startRow + rowOffset;
    while (_applicationImportRows.length <= rowIndex) _applicationImportRows.push(emptyApplicationImportRow());
    values.forEach(function(value, colOffset) {
      var key = hasHeader ? mappedKeys[colOffset] : (APPLICATION_IMPORT_COLUMNS[startCol + colOffset] || {}).key;
      if (key) _applicationImportRows[rowIndex][key] = String(value || "").trim();
    });
    _applicationImportRows[rowIndex]._error = "";
  });
  renderApplicationImportGrid();
  toast("已粘贴 " + pasted.length + " 行投递记录", "success");
}

function onApplicationImportPaste(event) {
  var text = event.clipboardData && event.clipboardData.getData("text/plain");
  if (!text || (!text.includes("\t") && !text.includes("\n"))) return;
  event.preventDefault();
  applyClipboardToApplicationImport(text);
}

async function pasteApplicationImportFromClipboard() {
  try {
    applyClipboardToApplicationImport(await navigator.clipboard.readText());
  } catch (_) {
    toast("浏览器未允许读取剪贴板，请点击第一个单元格后直接粘贴", "error");
  }
}

function chooseApplicationImportFile() {
  var input = document.createElement("input");
  input.type = "file";
  input.accept = ".xlsx,.csv";
  input.hidden = true;
  input.onchange = function() {
    if (input.files && input.files[0]) previewApplicationImportFile(input.files[0]);
    input.remove();
  };
  document.body.appendChild(input);
  input.click();
}

async function previewApplicationImportFile(file) {
  var formData = new FormData();
  formData.append("file", file);
  try {
    var preview = await API.upload("/api/applications/import/preview", formData);
    _applicationImportRows = (preview.rows || []).map(function(row) {
      return {
        company: row.company || "",
        title: row.title || "",
        applied_at: row.applied_at || "",
        _error: row._error || ""
      };
    });
    if (!_applicationImportRows.length) _applicationImportRows.push(emptyApplicationImportRow());
    renderApplicationImportGrid();
    var message = "已读取 " + _applicationImportRows.length + " 行";
    if ((preview.errors || []).length) message += "，其中 " + preview.errors.length + " 行需要修正";
    toast(message, preview.errors && preview.errors.length ? "error" : "success");
  } catch (error) {
    toast("读取失败：" + applicationImportErrorMessage(error), "error");
  }
}

function downloadApplicationImportTemplate() {
  var csv = "\ufeff公司名称,岗位名称,投递时间\n示例公司,产品经理,2026-10-10\n";
  var url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  var link = document.createElement("a");
  link.href = url;
  link.download = "投递记录导入模板.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function updateApplicationImportSummary() {
  var rows = _applicationImportRows.filter(applicationImportRowHasContent);
  var errorCount = rows.filter(function(row) { return row._error; }).length;
  var summary = document.getElementById("application-import-summary");
  if (!summary) return;
  summary.textContent = "当前 " + rows.length + " 条待导入" + (errorCount ? " · " + errorCount + " 条需修正" : "");
}

function validateApplicationImportRows() {
  var invalid = false;
  document.querySelectorAll(".application-import-table tbody tr").forEach(function(tr, index) {
    var row = _applicationImportRows[index];
    if (!applicationImportRowHasContent(row)) return;
    APPLICATION_IMPORT_COLUMNS.forEach(function(column, colIndex) {
      var missing = !String(row[column.key] || "").trim();
      var cell = tr.querySelectorAll("td")[colIndex + 1];
      if (cell) cell.classList.toggle("invalid", missing);
      if (missing) invalid = true;
    });
  });
  return !invalid;
}

async function submitApplicationImport() {
  if (_applicationImportSubmitting) return;
  var rows = _applicationImportRows.filter(applicationImportRowHasContent).map(function(row) {
    return { company: row.company, title: row.title, applied_at: row.applied_at };
  });
  if (!rows.length) {
    toast("请先填写或上传投递记录", "error");
    return;
  }
  if (!validateApplicationImportRows()) {
    toast("请补充标红行的必填信息", "error");
    return;
  }

  _applicationImportSubmitting = true;
  var button = document.getElementById("application-import-submit");
  if (button) { button.disabled = true; button.textContent = "导入中…"; }
  try {
    var result = await API.post("/api/applications/import/rows", { rows: rows });
    _applicationImportSubmitting = false;
    closeApplicationImport();
    refreshAfterApplicationImport();
    showApplicationImportResult(result);
  } catch (error) {
    _applicationImportSubmitting = false;
    if (button) { button.disabled = false; button.textContent = "确认导入"; }
    toast("导入失败：" + applicationImportErrorMessage(error), "error");
  }
}

function refreshAfterApplicationImport() {
  if (typeof _jobCache !== "undefined") _jobCache = null;
  if (typeof _jobCacheGroupId !== "undefined") _jobCacheGroupId = null;
  if (typeof _trackApplications !== "undefined") _trackApplications = null;
  if (typeof _renderedPages !== "undefined") _renderedPages.jobs = false;
  if (typeof markApplicationViewsStale === "function") markApplicationViewsStale();
  if (document.getElementById("page-track") && document.getElementById("page-track").classList.contains("active")) {
    loadApplications();
  }
}

function showApplicationImportResult(result) {
  var metrics = [
    ["成功导入", result.imported || 0, "success"],
    ["匹配岗位", result.matched_jobs || 0, ""],
    ["新增岗位", result.created_jobs || 0, ""],
    ["重复跳过", result.duplicates || 0, "muted"],
    ["需要修正", result.failed || 0, result.failed ? "error" : "muted"]
  ];
  var body = el("div", { class: "application-import-result" },
    el("p", { class: "muted" }, "投递记录已经和当前岗位库完成匹配，未匹配岗位已自动补入。"),
    el("div", { class: "application-import-result-grid" },
      ...metrics.map(function(metric) {
        return el("div", { class: "application-import-result-card " + metric[2] },
          el("strong", {}, metric[1]), el("span", {}, metric[0])
        );
      })
    ),
    result.errors && result.errors.length
      ? el("div", { class: "application-import-errors" },
          el("strong", {}, "需要修正的行"),
          el("ul", {}, ...result.errors.slice(0, 10).map(function(error) {
            return el("li", {}, "第 " + error.row + " 行：" + error.message);
          })),
          result.errors.length > 10 ? el("p", { class: "muted text-sm" }, "另有 " + (result.errors.length - 10) + " 条未展示") : null
        )
      : null
  );
  showModal("批量导入完成", body, [
    el("button", { class: "btn primary", onclick: closeModal }, "完成"),
    el("button", { class: "btn", onclick: function() { closeModal(); openApplicationImport(); } }, "继续导入")
  ]);
}

function applicationImportErrorMessage(error) {
  if (typeof parseApiError === "function") return parseApiError(error);
  return error && error.message ? error.message : "请稍后重试";
}
