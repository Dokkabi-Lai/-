var JOB_COLUMNS = [
  { key: "company", label: "公司", required: true, width: 150 },
  { key: "company_type", label: "公司类型", width: 110 },
  { key: "batch", label: "批次", width: 110 },
  { key: "location", label: "BASE", width: 110 },
  { key: "title", label: "岗位", required: true, width: 170 },
  { key: "description", label: "岗位 JD", width: 240 },
  { key: "url", label: "投递链接", width: 220 },
  { key: "open_date", label: "开始日期", width: 120 },
  { key: "close_date", label: "截止日期", width: 120 },
  { key: "apply_rule", label: "投递机制", width: 120 },
  { key: "referrer_code", label: "内推码", width: 110 },
  { key: "recorded_at", label: "记录时间", width: 140 }
];

var _jobGridRows = [];
var _jobGridActive = { row: 0, col: 0 };

function emptyJobGridRow() {
  var row = {};
  JOB_COLUMNS.forEach(function(column) { row[column.key] = ""; });
  return row;
}

function openJobGrid(prefill) {
  _jobGridRows = [];
  if (prefill) _jobGridRows.push(Object.assign(emptyJobGridRow(), prefill));
  while (_jobGridRows.length < 5) _jobGridRows.push(emptyJobGridRow());
  var overlay = el("div", { class: "job-grid-overlay", id: "job-grid-overlay" },
    el("div", { class: "job-grid-shell" },
      el("header", { class: "job-grid-header" },
        el("div", {},
          el("div", { class: "eyebrow" }, "COLLABORATIVE JOB SHEET"),
          el("h2", {}, "批量录入岗位"),
          el("p", { class: "muted" }, "可直接从 Excel 或飞书复制多行，点击第一个单元格后粘贴")
        ),
        el("div", { class: "job-grid-header-actions" },
          el("button", { class: "btn", onclick: pasteJobGridFromClipboard }, "从剪贴板粘贴"),
          el("button", { class: "btn", onclick: addJobGridRow }, "+ 添加行"),
          el("button", { class: "btn primary", onclick: submitJobGrid }, "保存到岗位库"),
          el("button", { class: "icon-btn grid-close", onclick: closeJobGrid, title: "关闭" }, "×")
        )
      ),
      el("div", { class: "job-grid-tip" },
        el("span", {}, "必填：公司、岗位"),
        el("span", { id: "job-grid-summary" }, "当前 0 条待保存")
      ),
      el("div", { class: "job-grid-scroll", id: "job-grid-scroll" })
    )
  );
  document.body.appendChild(overlay);
  renderJobGrid();
}

function closeJobGrid() {
  var overlay = document.getElementById("job-grid-overlay");
  if (overlay) overlay.remove();
}

function renderJobGrid() {
  var scroll = document.getElementById("job-grid-scroll");
  if (!scroll) return;
  scroll.innerHTML = "";
  var table = el("table", { class: "job-grid-table" });
  var head = el("thead", {}, el("tr", {},
    el("th", { class: "row-number" }, "#"),
    ...JOB_COLUMNS.map(function(column) {
      return el("th", { style: "min-width:" + column.width + "px" },
        column.label, column.required ? el("span", { class: "required-star" }, " *") : null
      );
    }),
    el("th", { class: "row-actions-col" }, "")
  ));
  var body = el("tbody");
  _jobGridRows.forEach(function(row, rowIndex) {
    var tr = el("tr", { class: "job-grid-row" },
      el("td", { class: "row-number" }, rowIndex + 1)
    );
    JOB_COLUMNS.forEach(function(column, colIndex) {
      var input = column.key === "description"
        ? el("textarea", { rows: "1" }, row[column.key] || "")
        : el("input", { value: row[column.key] || "", inputmode: column.key.includes("date") ? "numeric" : null });
      input.setAttribute("aria-label", column.label);
      input.onfocus = function() { _jobGridActive = { row: rowIndex, col: colIndex }; };
      input.oninput = function() {
        row[column.key] = this.value;
        this.closest("td").classList.remove("invalid");
        updateJobGridSummary();
      };
      input.onkeydown = function(event) {
        if (event.key === "Enter" && !event.shiftKey && column.key !== "description") {
          event.preventDefault();
          focusJobGridCell(rowIndex + 1, colIndex);
        }
      };
      tr.appendChild(el("td", { "data-label": column.label }, input));
    });
    tr.appendChild(el("td", { class: "row-actions-col" },
      el("button", { class: "icon-btn", title: "删除此行", onclick: function() { removeJobGridRow(rowIndex); } }, "×")
    ));
    body.appendChild(tr);
  });
  table.appendChild(head);
  table.appendChild(body);
  table.addEventListener("paste", onJobGridPaste);
  scroll.appendChild(table);
  updateJobGridSummary();
}

function addJobGridRow() {
  _jobGridRows.push(emptyJobGridRow());
  renderJobGrid();
  focusJobGridCell(_jobGridRows.length - 1, 0);
}

function removeJobGridRow(index) {
  _jobGridRows.splice(index, 1);
  if (!_jobGridRows.length) _jobGridRows.push(emptyJobGridRow());
  renderJobGrid();
}

function focusJobGridCell(row, col) {
  if (row >= _jobGridRows.length) {
    _jobGridRows.push(emptyJobGridRow());
    renderJobGrid();
  }
  var tr = document.querySelectorAll(".job-grid-table tbody tr")[row];
  var cell = tr && tr.querySelectorAll("td")[col + 1];
  var input = cell && cell.querySelector("input,textarea");
  if (input) input.focus();
}

function parseClipboardTable(text) {
  var rows = [], row = [], cell = "", quoted = false;
  for (var i = 0; i < text.length; i++) {
    var char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++; }
      else quoted = !quoted;
    } else if (char === "\t" && !quoted) {
      row.push(cell); cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else {
      cell += char;
    }
  }
  row.push(cell);
  if (row.some(function(value) { return value !== ""; })) rows.push(row);
  return rows;
}

function normalizeJobHeader(value) {
  return String(value || "").toLowerCase().replace(/\s/g, "");
}

var JOB_HEADER_ALIASES = {
  "公司": "company", "公司名称": "company", "公司类型": "company_type", "类型": "company_type",
  "批次": "batch", "base": "location", "地点": "location", "城市": "location",
  "岗位": "title", "岗位名称": "title", "职位": "title", "岗位jd": "description",
  "jd": "description", "岗位描述": "description", "投递链接": "url", "链接": "url",
  "开始日期": "open_date", "开放日期": "open_date", "截止日期": "close_date",
  "投递机制": "apply_rule", "内推码": "referrer_code", "记录时间": "recorded_at"
};

function applyClipboardToJobGrid(text) {
  var pasted = parseClipboardTable(text);
  if (!pasted.length) return;
  var first = pasted[0].map(normalizeJobHeader);
  var mappedKeys = first.map(function(header) { return JOB_HEADER_ALIASES[header] || null; });
  var hasHeader = mappedKeys.filter(Boolean).length >= 2 && mappedKeys.includes("company");
  if (hasHeader) pasted.shift();
  var startRow = _jobGridActive.row || 0;
  var startCol = _jobGridActive.col || 0;
  pasted.slice(0, 300).forEach(function(values, rowOffset) {
    var rowIndex = startRow + rowOffset;
    while (_jobGridRows.length <= rowIndex) _jobGridRows.push(emptyJobGridRow());
    values.forEach(function(value, colOffset) {
      var key = hasHeader ? mappedKeys[colOffset] : (JOB_COLUMNS[startCol + colOffset] || {}).key;
      if (key) _jobGridRows[rowIndex][key] = value.trim();
    });
  });
  renderJobGrid();
  toast("已粘贴 " + pasted.length + " 行", "success");
}

function onJobGridPaste(event) {
  var text = event.clipboardData && event.clipboardData.getData("text/plain");
  if (!text || (!text.includes("\t") && !text.includes("\n"))) return;
  event.preventDefault();
  applyClipboardToJobGrid(text);
}

async function pasteJobGridFromClipboard() {
  try {
    var text = await navigator.clipboard.readText();
    applyClipboardToJobGrid(text);
  } catch (_) {
    toast("浏览器未允许读取剪贴板，请点击单元格后直接粘贴", "error");
  }
}

function updateJobGridSummary() {
  var count = _jobGridRows.filter(function(row) { return row.company || row.title; }).length;
  var summary = document.getElementById("job-grid-summary");
  if (summary) summary.textContent = "当前 " + count + " 条待保存";
}

async function submitJobGrid() {
  var rows = _jobGridRows.filter(function(row) {
    return Object.keys(row).some(function(key) { return String(row[key] || "").trim(); });
  });
  var invalid = false;
  document.querySelectorAll(".job-grid-table tbody tr").forEach(function(tr, index) {
    var row = _jobGridRows[index];
    if (!row.company && !row.title) return;
    [0, 4].forEach(function(col) {
      var key = JOB_COLUMNS[col].key;
      var td = tr.querySelectorAll("td")[col + 1];
      td.classList.toggle("invalid", !String(row[key] || "").trim());
      if (!String(row[key] || "").trim()) invalid = true;
    });
  });
  if (invalid) { toast("请补充标红行的公司和岗位", "error"); return; }
  if (!rows.length) { toast("请先填写岗位", "error"); return; }
  try {
    var result = await API.post("/api/jobs/import/rows", { rows: rows });
    closeJobGrid();
    toast("已加入 " + result.total + " 条岗位", "success");
    load_jobs();
  } catch (e) {
    toast("保存失败：" + parseApiError(e), "error");
  }
}

