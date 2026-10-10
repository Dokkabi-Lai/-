window.load_jobs = async function() {
  var activeGroupId = getActiveGroupId();
  var cacheScope = String((currentUser && currentUser.id) || "anonymous") + ":" + String(activeGroupId);
  if (_jobCacheGroupId !== cacheScope) {
    _jobCache = null;
    _jobCacheTotal = 0;
    _jobCacheGroupId = cacheScope;
    _expandedJobCompanies = {};
  }
  var page = document.getElementById("page-jobs");
  page.innerHTML = "";
  var actions = el("div", { class: "header-actions", id: "jobs-header-actions" });
  actions.appendChild(el("button", { class: "btn", title: "获取群组里的最新岗位", onclick: function(event) {
    refreshJobs(event.currentTarget);
  } }, "↻ 刷新"));
  var sub = el("div", { class: "page-sub muted", id: "jobs-header-sub" }, "岗位由群主和管理员维护");

  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "岗位库"),
      sub
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

  loadJobs();
  API.get("/api/jobs/import/status").then(function(status) {
    window._canSyncJobs = !!status.can_sync;
    window._canManageJobs = !!status.can_manage;
    if (status.can_manage) {
      actions.appendChild(el("button", { class: "btn primary", onclick: openJobGrid }, "表格录入"));
      actions.appendChild(el("button", { class: "btn", onclick: function() { showAddJob(); } }, "+ 单条添加"));
    }
    if (status.can_sync) {
      actions.appendChild(el("button", { class: "btn", onclick: function() { pickExcelFile(); } }, "上传 Excel"));
      actions.appendChild(el("button", { class: "btn", onclick: function() { reloadExcel(); } }, "重新导入"));
    }
    if (status.uploaded_at) {
      sub.textContent = "最近上传：" + status.uploaded_at.replace("T", " ").slice(0, 16);
    } else if (status.can_manage) {
      sub.textContent = "上传 Excel 或表格录入，建立共享岗位库";
    }
    if (_jobCache) renderJobsFromCache();
  }).catch(function() {});
};

function loadFilterOptions() {
  if (!_jobCache) return;
  var batchSelect = document.getElementById("f-batch");
  var typeSelect = document.getElementById("f-type");
  if (!batchSelect || !typeSelect) return;
  var currentBatch = batchSelect.value;
  var currentType = typeSelect.value;
  var batches = {};
  var types = {};
  _jobCache.forEach(function(job) {
    if (job.batch) batches[job.batch] = (batches[job.batch] || 0) + 1;
    if (job.company_type) types[job.company_type] = (types[job.company_type] || 0) + 1;
  });
  batchSelect.innerHTML = "";
  typeSelect.innerHTML = "";
  batchSelect.appendChild(el("option", { value: "" }, "全部批次"));
  typeSelect.appendChild(el("option", { value: "" }, "全部类型"));
  Object.keys(batches).sort().forEach(function(name) {
    batchSelect.appendChild(el("option", { value: name }, name + " (" + batches[name] + ")"));
  });
  Object.keys(types).sort().forEach(function(name) {
    typeSelect.appendChild(el("option", { value: name }, name + " (" + types[name] + ")"));
  });
  batchSelect.value = currentBatch;
  typeSelect.value = currentType;
}

var _jobTimer;
var _jobApplyFilter = "all";
var _jobsRequestId = 0;
var _jobCache = null;
var _jobCacheTotal = 0;
var _jobCacheGroupId = null;
var _expandedJobCompanies = {};
function debounceJobs() { clearTimeout(_jobTimer); _jobTimer = setTimeout(loadJobs, 80); }

function setAppliedFilter(v) {
  _jobApplyFilter = v;
  ["all", "unapplied", "applied"].forEach(function(k) {
    var id = k === "all" ? "f-applied-all" : k === "unapplied" ? "f-applied-no" : "f-applied-yes";
    var btn = document.getElementById(id);
    if (btn) btn.classList.toggle("active", k === v);
  });
  loadJobs();
}

async function loadJobs(options) {
  options = options || {};
  var list = document.getElementById("job-list");
  if (!list) return;
  if (_jobCache && !options.refresh) {
    renderJobsFromCache();
    return;
  }
  var requestId = ++_jobsRequestId;
  // 一次取回轻量摘要，后续搜索、筛选、收藏和 Pass 都在浏览器内即时完成。
  // 这样不会在每次输入时往返远程数据库，也不会让列表闪白。
  var params = new URLSearchParams({ summary: "true", limit: "1000", hide_passed: "false" });
  if (!options.silent) list.innerHTML = '<div class="loading">加载中…</div>';
  try {
    var data = await API.get("/api/jobs?" + params);
    if (requestId !== _jobsRequestId) return;
    _jobCache = data.items || [];
    _jobCacheTotal = data.total || _jobCache.length;
    loadFilterOptions();
    renderJobsFromCache();
    return true;
  } catch(e) {
    if (requestId !== _jobsRequestId) return;
    list.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
    return false;
  }
}

function renderJobsFromCache() {
  var list = document.getElementById("job-list");
  if (!list || !_jobCache) return;
  var kw = val("f-kw");
  var loc = val("f-loc");
  var batch = val("f-batch");
  var companyType = val("f-type");
  var open = document.getElementById("f-open") && document.getElementById("f-open").checked;
  var showPassed = document.getElementById("f-show-passed") && document.getElementById("f-show-passed").checked;
  var favorite = document.getElementById("f-favorite") && document.getElementById("f-favorite").checked;
  var keyword = kw.toLowerCase();
  var location = loc.toLowerCase();
  var today = jobTodayValue();
  var items = _jobCache.filter(function(job) {
    if (!showPassed && job.passed) return false;
    if (favorite && !job.favorited) return false;
    if (_jobApplyFilter === "applied" && !job.applied) return false;
    if (_jobApplyFilter === "unapplied" && job.applied) return false;
    if (batch && job.batch !== batch) return false;
    if (companyType && job.company_type !== companyType) return false;
    if (open && job.close_date && job.close_date.slice(0, 10) < today) return false;
    if (location && !String(job.location || "").toLowerCase().includes(location)) return false;
    if (keyword) {
      var haystack = [job.company, job.title, job.location, job.batch, job.company_type, job.apply_rule]
        .filter(Boolean).join(" ").toLowerCase();
      if (!haystack.includes(keyword)) return false;
    }
    return true;
  });
  var count = document.getElementById("job-count");
  if (count) count.textContent = "显示 " + items.length + " 条" + (_jobCacheTotal > _jobCache.length ? "（前 " + _jobCache.length + " / " + _jobCacheTotal + "）" : "");
  if (!items.length) {
    list.innerHTML = "";
    list.appendChild(emptyState(_jobCache.length ? "没有匹配的岗位，换个条件试试" : "暂无岗位，点击「重新导入」从 Excel 加载"));
    return;
  }
  var groups = {};
  var order = [];
  items.forEach(function(job) {
    if (!groups[job.company]) { groups[job.company] = []; order.push(job.company); }
    groups[job.company].push(job);
  });
  var fragment = document.createDocumentFragment();
  order.forEach(function(company) { fragment.appendChild(companyGroup(company, groups[company])); });
  list.innerHTML = "";
  list.appendChild(fragment);
}

function jobTodayValue() {
  var now = new Date();
  var year = now.getFullYear();
  var month = String(now.getMonth() + 1).padStart(2, "0");
  var day = String(now.getDate()).padStart(2, "0");
  return year + "-" + month + "-" + day;
}

function cachedJob(id) {
  return (_jobCache || []).find(function(job) { return String(job.id) === String(id); });
}

async function refreshJobs(button) {
  if (button) { button.disabled = true; button.textContent = "刷新中…"; }
  try {
    var ok = await loadJobs({ refresh: true, silent: true });
    if (ok) toast("岗位库已是最新");
  } finally {
    if (button) { button.disabled = false; button.textContent = "↻ 刷新"; }
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
  headerRight.appendChild(el("button", { class: "btn sm", title: "在这家公司下增加岗位", onclick: function(e) {
    e.stopPropagation();
    showAddJob(meta);
  } }, "+ 岗位"));
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
  header.onclick = function() {
    this.parentElement.classList.toggle("collapsed");
    _expandedJobCompanies[company] = !this.parentElement.classList.contains("collapsed");
  };

  var jobList = el("div", { class: "company-jobs" });
  jobs.forEach(function(j) { jobList.appendChild(jobRow(j)); });
  return el("div", { class: "company-group" + (_expandedJobCompanies[company] ? "" : " collapsed") }, header, jobList);
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
        j.location ? el("span", { class: "info-chip" }, j.location) : null,
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
        ? el("button", { class: "btn sm ghost", title: "已记录投递", onclick: function(e) { e.stopPropagation(); showPage("track"); } }, "流程")
        : el("button", { class: "btn sm primary", title: "记录投递", onclick: function(e) { e.stopPropagation(); quickApply(j); } }, "投递"),
      el("button", {
        class: "icon-btn more-btn",
        title: "更多操作",
        onclick: function(e) { e.stopPropagation(); openJobMoreSheet(j); }
      }, "···")
    )
  );
}

function openJobMoreSheet(j) {
  var isPassed = !!j.passed;
  var sheet = el("div", { class: "action-sheet" },
    el("div", { class: "action-sheet-handle" }),
    el("div", { class: "action-sheet-title" }, j.company + " · " + j.title),
    el("button", { class: "action-sheet-item", onclick: function() { closeModal(); showJobDetail(j); } }, "查看详情"),
    j.url ? el("a", { class: "action-sheet-item", href: j.url, target: "_blank", onclick: closeModal }, "打开投递链接") : null,
    el("button", { class: "action-sheet-item", onclick: function() { closeModal(); togglePass(j.id); } }, isPassed ? "取消 Pass" : "标记 Pass"),
    el("button", { class: "action-sheet-item danger", onclick: function() { closeModal(); deleteJob(j); } }, "删除岗位"),
    el("button", { class: "action-sheet-cancel", onclick: closeModal }, "取消")
  );
  showModal("", sheet, [], { sheet: true });
}

async function showJobDetail(j) {
  if (!j._detailsLoaded) {
    showModal(j.company + " · " + j.title,
      el("div", { class: "loading" }, "正在加载岗位详情…"),
      [el("button", { class: "btn", onclick: closeModal }, "关闭")]
    );
    try {
      var details = await API.get("/api/jobs/" + j.id);
      Object.assign(j, details);
      j._detailsLoaded = true;
    } catch (e) {
      closeModal();
      toast("岗位详情加载失败，请稍后重试", "error");
      return;
    }
  }
  renderJobDetail(j);
}

function renderJobDetail(j) {
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
  if (j.requirements) {
    body.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "✓ 任职要求"),
      el("div", { class: "detail-content pre-wrap" }, j.requirements)
    ));
  }

  showModal(j.company + " · " + j.title, body, [
    el("button", { class: "btn primary", onclick: function() { quickApply(j); } }, "📝 记录投递"),
    el("button", { class: "btn danger", onclick: function() { deleteJob(j); } }, "删除岗位"),
    el("button", { class: "btn", onclick: closeModal }, "关闭")
  ]);
}

async function deleteJob(j) {
  if (!confirm("确定从岗位库删除「" + j.company + " · " + j.title + "」吗？仅群主或添加者可删除。")) return;
  try {
    await API.del("/api/jobs/" + j.id);
    toast("岗位已删除", "success");
    closeModal();
    _jobCache = (_jobCache || []).filter(function(job) { return String(job.id) !== String(j.id); });
    _jobCacheTotal = Math.max(0, _jobCacheTotal - 1);
    loadFilterOptions();
    renderJobsFromCache();
  } catch (e) {
    var msg = e.message || "";
    try { msg = JSON.parse(msg).detail || msg; } catch (_) {}
    toast("删除失败：" + msg, "error");
  }
}

function quickApply(j) {
  closeModal();
  var body = el("div", {},
    formRow("公司", el("input", { class: "input", id: "apply-company", value: j.company, readonly: true })),
    formRow("岗位", el("input", { class: "input", id: "apply-title", value: j.title, readonly: true })),
    formRow("投递日期", el("input", { class: "input", id: "apply-date", type: "date", value: jobTodayValue() })),
    formRow("投递渠道", el("input", { class: "input", id: "apply-channel", value: j.apply_rule || "", placeholder: "官网 / 内推 / 无限制投递" })),
    formRow("备注", el("textarea", { class: "textarea", id: "apply-notes", placeholder: "内推码、投递注意事项等", value: j.referrer_code ? "内推码: " + j.referrer_code : "" }))
  );
  showModal("记录投递 · " + j.company, body, [
    el("button", { class: "btn primary", onclick: async function(event) {
      var submitButton = event.currentTarget;
      submitButton.disabled = true;
      submitButton.textContent = "记录中…";
      try {
        var created = await API.post("/api/applications", {
          company: j.company, title: j.title, job_id: j.id,
          applied_at: val("apply-date") || jobTodayValue(),
          channel: val("apply-channel") || null,
          notes: val("apply-notes") || null
        });
        toast("已记录投递！去流程跟踪查看 →");
        closeModal();
        if (typeof syncTrackApplication === "function") syncTrackApplication(created);
        if (typeof invalidatePages === "function") invalidatePages();
        var cached = cachedJob(j.id);
        if (cached) cached.applied = true;
        renderJobsFromCache();
      } catch(e) {
        submitButton.disabled = false;
        submitButton.textContent = "确认投递";
        toast("失败: " + e.message);
      }
    } }, "确认投递"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function toggleCompanyPass(company) {
  try {
    var result = await API.post("/api/jobs/pass-company", { company: company });
    (_jobCache || []).forEach(function(job) {
      if (job.company === company) job.passed = result.passed;
    });
    toast("已更新 " + company);
    renderJobsFromCache();
  } catch(e) { toast("操作失败: " + e.message); }
}

async function togglePass(id) {
  try {
    var r = await API.post("/api/jobs/" + id + "/pass");
    var job = cachedJob(id);
    if (job) job.passed = r.passed;
    toast(r.passed ? "已标记Pass" : "已取消Pass");
    renderJobsFromCache();
  } catch(e) { toast("操作失败"); }
}

async function toggleFav(id) {
  try {
    var r = await API.post("/api/jobs/" + id + "/favorite");
    var job = cachedJob(id);
    if (job) job.favorited = r.favorited;
    toast(r.favorited ? "已收藏" : "已取消收藏");
    renderJobsFromCache();
  } catch(e) { toast("操作失败"); }
}

function showAddJob(prefill) {
  prefill = prefill || {};
  var body = el("div", {},
    formRow("公司名称 *", el("input", { class: "input", id: "add-j-company", value: prefill.company || "" })),
    formRow("公司类型", el("input", { class: "input", id: "add-j-type", value: prefill.company_type || "", placeholder: "互联网 / 车企" })),
    formRow("批次", el("input", { class: "input", id: "add-j-batch", value: prefill.batch || "", placeholder: "正式批" })),
    formRow("BASE", el("input", { class: "input", id: "add-j-loc", value: prefill.location || "", placeholder: "上海 / 杭州" })),
    formRow("岗位名称 *", el("input", { class: "input", id: "add-j-title" })),
    formRow("投递机制", el("input", { class: "input", id: "add-j-rule", value: prefill.apply_rule || "", placeholder: "官网 / 内推 / 不限投" })),
    formRow("开始日期", el("input", { class: "input", id: "add-j-open", type: "date" })),
    formRow("截止日期", el("input", { class: "input", id: "add-j-close", type: "date" })),
    formRow("投递链接", el("input", { class: "input", id: "add-j-url", value: prefill.url || "", placeholder: "https://..." })),
    formRow("内推码", el("input", { class: "input", id: "add-j-ref" })),
    formRow("岗位 JD", el("textarea", { class: "textarea", id: "add-j-desc" }))
  );
  showModal("手动添加岗位", body, [
    el("button", { class: "btn primary", onclick: function(event) { submitAddJob(event.currentTarget); } }, "保存"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function submitAddJob(button) {
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
  if (button) { button.disabled = true; button.textContent = "保存中…"; }
  try {
    var created = await API.post("/api/jobs", data);
    created.applied = false;
    created.favorited = false;
    created.passed = false;
    created._detailsLoaded = true;
    if (!_jobCache) _jobCache = [];
    _jobCache.unshift(created);
    _jobCacheTotal += 1;
    closeModal();
    toast("岗位已添加");
    loadFilterOptions();
    renderJobsFromCache();
  } catch (e) {
    if (button) { button.disabled = false; button.textContent = "保存"; }
    toast("添加失败: " + parseApiError(e));
  }
}

async function reloadExcel() {
  toast("正在导入岗位…");
  try {
    var r = await API.post("/api/jobs/import/reload");
    toast("导入完成：新增 " + r.created + "，更新 " + r.updated);
    _jobCache = null;
    loadJobs({ refresh: true });
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
    _jobCache = null;
    loadJobs({ refresh: true });
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
