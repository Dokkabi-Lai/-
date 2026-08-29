window.load_jobs = async function() {
  var page = document.getElementById("page-jobs");
  page.innerHTML = "";
  var status = {};
  try { status = await API.get("/api/jobs/import/status"); } catch (e) {}
  window._canSyncJobs = !!status.can_sync;

  var actions = el("div", { class: "header-actions" });
  if (status.can_manage) {
    actions.appendChild(el("button", { class: "btn primary", onclick: openJobGrid }, "表格录入"));
    actions.appendChild(el("button", { class: "btn", onclick: function() { showAddJob(); } }, "+ 单条添加"));
  }
  if (status.can_sync) {
    actions.appendChild(el("button", { class: "btn", onclick: function() { pickExcelFile(); } }, "上传 Excel"));
    actions.appendChild(el("button", { class: "btn", onclick: function() { reloadExcel(); } }, "重新导入"));
  }

  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "岗位库"),
      el("div", { class: "page-sub muted" },
        status.uploaded_at
          ? "最近上传：" + status.uploaded_at.replace("T", " ").slice(0, 16)
          : status.can_manage ? "上传 Excel 或表格录入，建立共享岗位库" : "岗位由群主和管理员维护"
      )
    ),
    actions
  ));

  var batchSelect = el("select", { class: "input filter-input sm", id: "f-batch", onchange: function() { loadJobs(); } },
    el("option", { value: "" }, "全部批次")
  );
  var typeSelect = el("select", { class: "input filter-input sm", id: "f-type", onchange: function() { loadJobs(); } },
    el("option", { value: "" }, "全部类型")
  );

  page.appendChild(el("div", { class: "filter-bar card" },
    el("div", { class: "filter-row" },
      el("input", { class: "input filter-input", id: "f-kw", placeholder: "🔍 搜索公司或岗位...", oninput: function() { debounceJobs(); } }),
      el("input", { class: "input filter-input sm", id: "f-loc", placeholder: "📍 BASE", oninput: function() { debounceJobs(); } }),
      batchSelect,
      typeSelect
    ),
    el("div", { class: "filter-chips" },
      el("div", { class: "filter-tabs" },
        el("button", { class: "tab-btn active", id: "f-applied-all", onclick: function() { setAppliedFilter("all"); } }, "全部"),
        el("button", { class: "tab-btn", id: "f-applied-no", onclick: function() { setAppliedFilter("unapplied"); } }, "未投递"),
        el("button", { class: "tab-btn", id: "f-applied-yes", onclick: function() { setAppliedFilter("applied"); } }, "已投递")
      ),
      el("label", { class: "chip-toggle" },
        el("input", { type: "checkbox", id: "f-open", onchange: function() { loadJobs(); } }),
        el("span", {}, "仅可投递")
      ),
      el("label", { class: "chip-toggle" },
        el("input", { type: "checkbox", id: "f-show-passed", onchange: function() { loadJobs(); } }),
        el("span", {}, "显示已Pass")
      ),
      el("label", { class: "chip-toggle" },
        el("input", { type: "checkbox", id: "f-favorite", onchange: function() { loadJobs(); } }),
        el("span", {}, "只看收藏")
      ),
      el("span", { class: "muted text-sm", id: "job-count" })
    )
  ));
  page.appendChild(el("div", { id: "job-list" }, el("div", { class: "loading" }, "加载中…")));

  await loadFilterOptions();
  loadJobs();
};

async function loadFilterOptions() {
  try {
    var batches = await API.get("/api/jobs/batches/list");
    var batchSelect = document.getElementById("f-batch");
    batches.forEach(function(b) {
      batchSelect.appendChild(el("option", { value: b.batch }, b.batch + " (" + b.count + ")"));
    });
    var types = await API.get("/api/jobs/company-types/list");
    var typeSelect = document.getElementById("f-type");
    types.forEach(function(t) {
      typeSelect.appendChild(el("option", { value: t.company_type }, t.company_type + " (" + t.count + ")"));
    });
  } catch(e) {}
}

var _jobTimer;
var _jobApplyFilter = "all";
function debounceJobs() { clearTimeout(_jobTimer); _jobTimer = setTimeout(loadJobs, 300); }

function setAppliedFilter(v) {
  _jobApplyFilter = v;
  ["all", "unapplied", "applied"].forEach(function(k) {
    var id = k === "all" ? "f-applied-all" : k === "unapplied" ? "f-applied-no" : "f-applied-yes";
    var btn = document.getElementById(id);
    if (btn) btn.classList.toggle("active", k === v);
  });
  loadJobs();
}

async function loadJobs() {
  var list = document.getElementById("job-list");
  if (!list) return;
  var kw = val("f-kw");
  var loc = val("f-loc");
  var batch = val("f-batch");
  var companyType = val("f-type");
  var open = document.getElementById("f-open").checked;
  var showPassed = document.getElementById("f-show-passed").checked;
  var favorite = document.getElementById("f-favorite").checked;
  var params = new URLSearchParams();
  if (kw) params.set("keyword", kw);
  if (loc) params.set("location", loc);
  if (batch) params.set("batch", batch);
  if (companyType) params.set("company_type", companyType);
  if (open) params.set("only_open", "true");
  if (showPassed) params.set("hide_passed", "false");
  if (favorite) params.set("favorited", "true");
  if (_jobApplyFilter !== "all") params.set("applied", _jobApplyFilter);
  params.set("limit", "500");
  list.innerHTML = '<div class="loading">加载中…</div>';
  try {
    var data = await API.get("/api/jobs?" + params);
    document.getElementById("job-count").textContent = "共 " + data.total + " 条";
    if (!data.items.length) {
      list.innerHTML = "";
      list.appendChild(emptyState("暂无岗位，点击「重新导入」从 Excel 加载"));
      return;
    }

    var groups = {};
    var order = [];
    data.items.forEach(function(j) {
      if (!groups[j.company]) { groups[j.company] = []; order.push(j.company); }
      groups[j.company].push(j);
    });

    list.innerHTML = "";
    order.forEach(function(company) {
      list.appendChild(companyGroup(company, groups[company]));
    });
  } catch(e) {
    list.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

function companyGroup(company, jobs) {
  var meta = jobs[0];
  var appliedCount = jobs.filter(function(j) { return j.applied; }).length;
  var loc = meta.location;
  var closeLabel = formatCloseDate(meta);
  var officialUrl = meta.url;
  var allPassed = jobs.every(function(j) { return j.passed; });

  var headerRight = el("div", { class: "company-right" });
  if (meta.batch) headerRight.appendChild(el("span", { class: "batch-chip" }, meta.batch));
  if (meta.company_type) headerRight.appendChild(el("span", { class: "chip sm" }, meta.company_type));
  if (closeLabel) headerRight.appendChild(el("span", { class: "deadline-chip" }, closeLabel));
  if (officialUrl) {
    headerRight.appendChild(el("a", { href: officialUrl, target: "_blank", class: "btn sm", onclick: function(e) { e.stopPropagation(); } }, "🔗 投递"));
  }
  headerRight.appendChild(el("button", { class: "btn sm" + (allPassed ? " active" : ""), onclick: function(e) { e.stopPropagation(); toggleCompanyPass(company); } }, allPassed ? "✅ 已Pass" : "👋 Pass"));
  headerRight.appendChild(el("div", { class: "company-arrow" }, "▾"));

  var header = el("div", { class: "company-header" },
    el("div", { class: "company-left" },
      el("div", { class: "company-avatar" }, company.charAt(0)),
      el("div", {},
        el("div", { class: "company-name" }, company),
        el("div", { class: "company-meta muted text-sm" },
          jobs.length + " 个岗位",
          appliedCount ? " · " + appliedCount + " 已投递" : " · 尚未投递",
          loc ? " · 📍 " + loc : "",
          meta.referrer_code ? " · 内推 " + meta.referrer_code : ""
        )
      )
    ),
    headerRight
  );
  header.onclick = function() { this.parentElement.classList.toggle("collapsed"); };

  var jobList = el("div", { class: "company-jobs" });
  jobs.forEach(function(j) { jobList.appendChild(jobRow(j)); });
  return el("div", { class: "company-group collapsed" }, header, jobList);
}

function formatCloseDate(j) {
  if (j.close_date) {
    var dl = daysLeft(j.close_date);
    if (dl !== null) return dl < 0 ? "已截止" : "剩" + dl + "天";
    return "截止 " + fmtDate(j.close_date);
  }
  return j.close_date_text || null;
}

function jobRow(j) {
  var isPassed = j.passed;
  var applied = !!j.applied;
  return el("div", { class: "job-row" + (isPassed ? " passed" : "") + (applied ? " applied-row" : "") },
    el("div", { class: "job-row-main", onclick: function() { showJobDetail(j); } },
      el("div", { class: "job-row-title" }, j.title),
      el("div", { class: "job-row-info" },
        el("span", { class: "chip sm " + (applied ? "applied" : "unapplied") }, applied ? "已投递" : "未投递"),
        j.batch ? el("span", { class: "info-chip batch-chip" }, j.batch) : null,
        j.location ? el("span", { class: "info-chip" }, "📍 " + j.location) : null,
        j.apply_rule ? el("span", { class: "info-chip" }, j.apply_rule) : null,
        formatCloseDate(j) ? el("span", { class: "info-chip" }, formatCloseDate(j)) : null
      )
    ),
    el("div", { class: "job-row-actions" },
      el("button", {
        class: "icon-btn favorite" + (j.favorited ? " active" : ""),
        title: j.favorited ? "取消收藏" : "收藏",
        onclick: function(e) { e.stopPropagation(); toggleFav(j.id); }
      }, j.favorited ? "★" : "☆"),
      applied
        ? el("button", { class: "btn sm", title: "已记录投递", onclick: function(e) { e.stopPropagation(); showPage("track"); } }, "查看流程")
        : el("button", { class: "btn sm primary", title: "记录投递", onclick: function(e) { e.stopPropagation(); quickApply(j); } }, "投递"),
      j.url ? el("a", { href: j.url, target: "_blank", class: "btn sm", title: "官网投递", onclick: function(e) { e.stopPropagation(); } }, "链接") : null,
      el("button", { class: "btn sm" + (isPassed ? " active" : ""), title: isPassed ? "取消Pass" : "Pass", onclick: function(e) { e.stopPropagation(); togglePass(j.id); } }, isPassed ? "已Pass" : "Pass")
    )
  );
}

function showJobDetail(j) {
  var body = el("div", { class: "job-detail" },
    el("div", { class: "job-detail-header" },
      el("div", { class: "company-avatar lg" }, j.company.charAt(0)),
      el("div", {},
        el("h3", {}, j.company),
        el("h4", { class: "muted" }, j.title)
      )
    ),
    el("div", { class: "job-detail-chips" },
      j.company_type ? el("span", { class: "chip" }, j.company_type) : null,
      j.batch ? el("span", { class: "chip" }, j.batch) : null,
      j.location ? el("span", { class: "chip" }, "📍 " + j.location) : null,
      j.apply_rule ? el("span", { class: "chip" }, j.apply_rule) : null,
      j.referrer_code ? el("span", { class: "chip" }, "内推码: " + j.referrer_code) : null,
      j.open_date ? el("span", { class: "chip" }, "开放: " + fmtDate(j.open_date)) : null,
      formatCloseDate(j) ? el("span", { class: "chip" }, "截止: " + formatCloseDate(j)) : null
    ),
    j.url ? el("div", { class: "mt-12" },
      el("a", { href: j.url, target: "_blank", class: "btn sm primary" }, "🔗 前往投递 ↗")
    ) : null
  );

  if (j.description) {
    body.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "📋 岗位 JD"),
      el("div", { class: "detail-content pre-wrap" }, j.description)
    ));
  }

  showModal(j.company + " · " + j.title, body, [
    el("button", { class: "btn primary", onclick: function() { quickApply(j); } }, "📝 记录投递"),
    el("button", { class: "btn", onclick: closeModal }, "关闭")
  ]);
}

function quickApply(j) {
  closeModal();
  var body = el("div", {},
    formRow("公司", el("input", { class: "input", id: "apply-company", value: j.company, readonly: true })),
    formRow("岗位", el("input", { class: "input", id: "apply-title", value: j.title, readonly: true })),
    formRow("投递渠道", el("input", { class: "input", id: "apply-channel", value: j.apply_rule || "", placeholder: "官网 / 内推 / 无限制投递" })),
    formRow("备注", el("textarea", { class: "textarea", id: "apply-notes", placeholder: "内推码、投递注意事项等", value: j.referrer_code ? "内推码: " + j.referrer_code : "" }))
  );
  showModal("记录投递 · " + j.company, body, [
    el("button", { class: "btn primary", onclick: async function() {
      try {
        await API.post("/api/applications", {
          company: j.company, title: j.title, job_id: j.id,
          channel: val("apply-channel") || null,
          notes: val("apply-notes") || null
        });
        toast("已记录投递！去流程跟踪查看 →");
        closeModal();
        loadJobs();
      } catch(e) { toast("失败: " + e.message); }
    } }, "确认投递"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function toggleCompanyPass(company) {
  try {
    await API.post("/api/jobs/pass-company", { company: company });
    toast("已更新 " + company);
    loadJobs();
  } catch(e) { toast("操作失败: " + e.message); }
}

async function togglePass(id) {
  try {
    var r = await API.post("/api/jobs/" + id + "/pass");
    toast(r.passed ? "已标记Pass" : "已取消Pass");
    loadJobs();
  } catch(e) { toast("操作失败"); }
}

async function toggleFav(id) {
  try {
    var r = await API.post("/api/jobs/" + id + "/favorite");
    toast(r.favorited ? "已收藏" : "已取消收藏");
    loadJobs();
  } catch(e) { toast("操作失败"); }
}

function showAddJob() {
  var body = el("div", {},
    formRow("公司名称 *", el("input", { class: "input", id: "add-j-company" })),
    formRow("公司类型", el("input", { class: "input", id: "add-j-type", placeholder: "互联网 / 车企" })),
    formRow("批次", el("input", { class: "input", id: "add-j-batch", placeholder: "正式批" })),
    formRow("BASE", el("input", { class: "input", id: "add-j-loc", placeholder: "上海 / 杭州" })),
    formRow("岗位名称 *", el("input", { class: "input", id: "add-j-title" })),
    formRow("投递机制", el("input", { class: "input", id: "add-j-rule", placeholder: "官网 / 内推 / 不限投" })),
    formRow("开始日期", el("input", { class: "input", id: "add-j-open", type: "date" })),
    formRow("截止日期", el("input", { class: "input", id: "add-j-close", type: "date" })),
    formRow("投递链接", el("input", { class: "input", id: "add-j-url", placeholder: "https://..." })),
    formRow("内推码", el("input", { class: "input", id: "add-j-ref" })),
    formRow("岗位 JD", el("textarea", { class: "textarea", id: "add-j-desc" }))
  );
  showModal("手动添加岗位", body, [
    el("button", { class: "btn primary", onclick: function() { submitAddJob(); } }, "保存"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function submitAddJob() {
  var data = {
    company: val("add-j-company"), title: val("add-j-title"),
    company_type: val("add-j-type") || null,
    batch: val("add-j-batch") || null,
    location: val("add-j-loc") || null,
    description: val("add-j-desc") || null,
    open_date: val("add-j-open") || null,
    close_date: val("add-j-close") || null,
    apply_rule: val("add-j-rule") || null,
    url: val("add-j-url") || null,
    referrer_code: val("add-j-ref") || null
  };
  if (!data.company || !data.title) { toast("请填写公司和岗位名称"); return; }
  await API.post("/api/jobs", data);
  closeModal();
  toast("岗位已添加");
  loadJobs();
}

async function reloadExcel() {
  toast("正在导入岗位…");
  try {
    var r = await API.post("/api/jobs/import/reload");
    toast("导入完成：新增 " + r.created + "，更新 " + r.updated);
    load_jobs();
  } catch(e) { toast("导入失败: " + parseApiError(e)); }
}

function pickExcelFile() {
  var input = document.getElementById("excel-file-input");
  if (!input) return;
  input.onchange = function() {
    if (input.files && input.files[0]) uploadExcelFile(input.files[0]);
    input.value = "";
  };
  input.click();
}

async function uploadExcelFile(file) {
  toast("正在上传「" + file.name + "」…");
  var fd = new FormData();
  fd.append("file", file);
  try {
    var r = await API.upload("/api/jobs/import/upload", fd);
    toast("导入完成：新增 " + r.created + "，更新 " + r.updated);
    load_jobs();
  } catch(e) { toast("导入失败: " + parseApiError(e)); }
}

function parseApiError(e) {
  var m = (e && e.message) || "未知错误";
  try {
    var j = JSON.parse(m);
    return j.detail || m;
  } catch (x) { return m; }
}

(function setupExcelDrop() {
  var overlay = document.getElementById("drop-overlay");
  if (!overlay) return;
  var dragCount = 0;
  document.addEventListener("dragenter", function(e) {
    if (![].some.call(e.dataTransfer.types || [], function(t) { return t === "Files"; })) return;
    dragCount += 1;
    overlay.classList.add("show");
  });
  document.addEventListener("dragleave", function() {
    dragCount = Math.max(0, dragCount - 1);
    if (!dragCount) overlay.classList.remove("show");
  });
  document.addEventListener("dragover", function(e) { e.preventDefault(); });
  document.addEventListener("drop", function(e) {
    e.preventDefault();
    dragCount = 0;
    overlay.classList.remove("show");
    var file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    if (!window._canSyncJobs) { toast("只有群主可以上传整份 Excel", "error"); return; }
    if (!/\.xlsx?$/i.test(file.name)) { toast("请上传 .xlsx 表格"); return; }
    uploadExcelFile(file);
  });
})();
