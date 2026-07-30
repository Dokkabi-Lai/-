window.load_jobs = async function() {
  var page = document.getElementById("page-jobs");
  page.innerHTML = "";
  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "岗位浏览"),
      el("div", { class: "page-sub muted" }, "按公司浏览校招岗位，点击公司展开查看子岗位")
    ),
    el("div", { class: "header-actions" },
      el("button", { class: "btn", onclick: function() { runSpiderNow(); } }, "🔄 抓取最新"),
      el("button", { class: "btn primary", onclick: function() { showAddJob(); } }, "+ 手动添加")
    )
  ));

  var filterBar = el("div", { class: "filter-bar card" },
    el("div", { class: "filter-row" },
      el("input", { class: "input filter-input", id: "f-kw", placeholder: "🔍 搜索公司或岗位名称...", oninput: function() { debounceJobs(); } }),
      el("input", { class: "input filter-input sm", id: "f-loc", placeholder: "📍 城市", oninput: function() { debounceJobs(); } }),
      el("select", { class: "input filter-input sm", id: "f-batch", onchange: function() { loadJobs(); } },
        el("option", { value: "" }, "全部批次"),
        el("option", { value: "27届提前批" }, "27届提前批"),
        el("option", { value: "27届秋招" }, "27届秋招"),
        el("option", { value: "27届秋招补录" }, "27届秋招补录"),
        el("option", { value: "27届校招" }, "27届校招")
      )
    ),
    el("div", { class: "filter-chips" },
      el("label", { class: "chip-toggle" },
        el("input", { type: "checkbox", id: "f-open", onchange: function() { loadJobs(); } }),
        el("span", {}, "仅可投递")
      ),
      el("label", { class: "chip-toggle" },
        el("input", { type: "checkbox", id: "f-show-passed", onchange: function() { loadJobs(); } }),
        el("span", {}, "显示已Pass")
      ),
      el("span", { class: "muted text-sm", id: "job-count" })
    )
  );
  page.appendChild(filterBar);
  page.appendChild(el("div", { id: "job-list" }, el("div", { class: "loading" }, "加载中…")));
  loadJobs();
};

var _jobTimer;
function debounceJobs() { clearTimeout(_jobTimer); _jobTimer = setTimeout(loadJobs, 300); }

async function loadJobs() {
  var list = document.getElementById("job-list");
  if (!list) return;
  var kw = val("f-kw");
  var loc = val("f-loc");
  var batch = val("f-batch");
  var open = document.getElementById("f-open").checked;
  var showPassed = document.getElementById("f-show-passed").checked;
  var params = new URLSearchParams();
  if (kw) params.set("keyword", kw);
  if (loc) params.set("location", loc);
  if (batch) params.set("batch", batch);
  if (open) params.set("only_open", "true");
  if (showPassed) params.set("hide_passed", "false");
  params.set("limit", "500");
  list.innerHTML = '<div class="loading">加载中…</div>';
  try {
    var data = await API.get("/api/jobs?" + params);
    document.getElementById("job-count").textContent = "共 " + data.total + " 条";
    if (!data.items.length) { list.innerHTML = ""; list.appendChild(emptyState("暂无岗位，点击「抓取最新」获取校招信息")); return; }

    // 按公司分组
    var groups = {};
    var order = [];
    data.items.forEach(function(j) {
      if (!groups[j.company]) { groups[j.company] = { jobs: [], meta: null }; order.push(j.company); }
      // 如果 title 是 "xxx校招"，作为公司的元数据
      if (j.title === j.company + "校招") {
        groups[j.company].meta = j;
      } else {
        groups[j.company].jobs.push(j);
      }
    });

    list.innerHTML = "";
    order.forEach(function(company) {
      var group = groups[company];
      list.appendChild(companyGroup(company, group.jobs, group.meta));
    });
  } catch(e) {
    list.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

function companyGroup(company, jobs, meta) {
  // meta 是公司级别的信息（日期、地点、链接等）
  var hasJobs = jobs.length > 0;
  var totalCount = hasJobs ? jobs.length : 0;
  var metaInfo = meta || (hasJobs ? jobs[0] : null);
  var loc = metaInfo ? metaInfo.location : null;
  var closeDate = metaInfo ? metaInfo.close_date : null;
  var officialUrl = metaInfo ? metaInfo.url : (hasJobs ? jobs[0].url : null);
  var dl = daysLeft(closeDate);

  // 检查公司是否所有岗位都被pass
  var allPassed = (meta && meta.passed) || false;
  var batchLabel = metaInfo ? metaInfo.batch : null;

  // 公司头部
  var headerRight = el("div", { class: "company-right" });
  if (batchLabel) {
    headerRight.appendChild(el("span", { class: "batch-chip" }, batchLabel));
  }
  if (dl !== null) {
    var cls = dl <= 3 ? "urgent" : dl <= 7 ? "warn" : "";
    headerRight.appendChild(el("span", { class: "deadline-chip " + cls }, dl < 0 ? "已截止" : dl === 0 ? "今天截止" : "剩" + dl + "天"));
  }
  if (officialUrl) {
    var linkBtn = el("a", { href: officialUrl, target: "_blank", class: "btn sm", onclick: function(e) { e.stopPropagation(); } }, "🔗 官网");
    headerRight.appendChild(linkBtn);
  }
  // 公司级Pass按钮
  var passBtn = el("button", { class: "btn sm" + (allPassed ? " active" : ""), title: allPassed ? "取消Pass公司" : "Pass整个公司", onclick: function(e) { e.stopPropagation(); toggleCompanyPass(company, jobs, meta); } }, allPassed ? "✅ 已Pass" : "👋 Pass");
  headerRight.appendChild(passBtn);
  headerRight.appendChild(el("div", { class: "company-arrow" }, "▾"));

  var header = el("div", { class: "company-header" },
    el("div", { class: "company-left" },
      el("div", { class: "company-avatar" }, company.charAt(0)),
      el("div", {},
        el("div", { class: "company-name" }, company),
        el("div", { class: "company-meta muted text-sm" },
          hasJobs ? totalCount + " 个岗位" : "暂无具体岗位",
          loc ? " · 📍 " + loc : ""
        )
      )
    ),
    headerRight
  );
  header.onclick = function() { this.parentElement.classList.toggle("collapsed"); };

  var jobList = el("div", { class: "company-jobs" });

  if (hasJobs) {
    jobs.forEach(function(j) { jobList.appendChild(jobRow(j)); });
  } else if (meta) {
    // 只有公司级信息，没有具体岗位
    jobList.appendChild(el("div", { class: "no-sub-jobs" },
      el("div", { class: "muted text-sm" },
        meta.description ? meta.description : "该公司暂未抓取到具体岗位信息"
      ),
      officialUrl ? el("div", { class: "mt-8" },
        el("a", { href: officialUrl, target: "_blank", class: "btn sm" }, "🔗 去官网查看具体岗位")
      ) : null
    ));
  }

  // 添加子岗位按钮
  jobList.appendChild(el("div", { class: "add-sub-job" },
    el("button", { class: "btn sm", onclick: function(e) { e.stopPropagation(); showAddSubJob(company, metaInfo); } }, "+ 添加岗位")
  ));

  return el("div", { class: "company-group collapsed" }, header, jobList);
}

function jobRow(j) {
  var isPassed = j.passed;
  var dl = daysLeft(j.close_date);
  return el("div", { class: "job-row" + (isPassed ? " passed" : "") },
    el("div", { class: "job-row-main", onclick: function() { showJobDetail(j); } },
      el("div", { class: "job-row-title" }, j.title),
      el("div", { class: "job-row-info" },
        j.batch ? el("span", { class: "info-chip batch-chip" }, j.batch) : null,
        j.location ? el("span", { class: "info-chip" }, "📍 " + j.location) : null,
        j.salary ? el("span", { class: "info-chip" }, "💰 " + j.salary) : null,
        j.open_date ? el("span", { class: "info-chip" }, "🕐 " + fmtDate(j.open_date)) : null,
        dl !== null ? el("span", { class: "info-chip " + (dl <= 3 ? "urgent" : dl <= 7 ? "warn" : "") },
          dl < 0 ? "已截止" : dl === 0 ? "今天截止" : "剩" + dl + "天") : null
      )
    ),
    el("div", { class: "job-row-actions" },
      el("button", { class: "btn sm primary", title: "记录投递", onclick: function(e) { e.stopPropagation(); quickApply(j); } }, "📝 投递"),
      j.url ? el("a", { href: j.url, target: "_blank", class: "btn sm", title: "官网投递", onclick: function(e) { e.stopPropagation(); } }, "🔗") : null,
      el("button", { class: "btn sm" + (isPassed ? " active" : ""), title: isPassed ? "取消Pass" : "Pass", onclick: function(e) { e.stopPropagation(); togglePass(j.id); } }, isPassed ? "✅" : "👋"),
      el("button", { class: "btn sm icon-btn", title: j.favorited ? "取消收藏（从待投递移除）" : "收藏并加入待投递", onclick: function(e) { e.stopPropagation(); toggleFav(j.id); } }, j.favorited ? "⭐" : "☆")
    )
  );
}

function showAddSubJob(company, meta) {
  var body = el("div", {},
    formRow("公司", el("input", { class: "input", id: "sub-company", value: company, readonly: true })),
    formRow("岗位名称 *", el("input", { class: "input", id: "sub-title", placeholder: "如：后端开发工程师" })),
    formRow("工作地点", el("input", { class: "input", id: "sub-loc", value: (meta && meta.location) || "", placeholder: "北京" })),
    formRow("薪资", el("input", { class: "input", id: "sub-salary", placeholder: "如 15-25K" })),
    formRow("官网投递链接", el("input", { class: "input", id: "sub-url", value: (meta && meta.url) || "", placeholder: "https://..." })),
    formRow("截止日期", el("input", { class: "input", id: "sub-close", type: "date", value: (meta && meta.close_date) || "" })),
    formRow("岗位描述", el("textarea", { class: "textarea", id: "sub-desc", placeholder: "岗位职责和描述" })),
    formRow("岗位要求", el("textarea", { class: "textarea", id: "sub-req", placeholder: "学历要求、技能要求等" }))
  );
  showModal("添加岗位 · " + company, body, [
    el("button", { class: "btn primary", onclick: function() { submitAddSubJob(company); } }, "保存"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function submitAddSubJob(company) {
  var title = val("sub-title");
  if (!title) { toast("请填写岗位名称"); return; }
  await API.post("/api/jobs", {
    company: company, title: title,
    location: val("sub-loc") || null, salary: val("sub-salary") || null,
    url: val("sub-url") || null, close_date: val("sub-close") || null,
    description: val("sub-desc") || null, requirements: val("sub-req") || null
  });
  closeModal();
  toast("岗位已添加");
  loadJobs();
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
      j.location ? el("span", { class: "chip" }, "📍 " + j.location) : null,
      j.salary ? el("span", { class: "chip" }, "💰 " + j.salary) : null,
      j.open_date ? el("span", { class: "chip" }, "开放: " + fmtDate(j.open_date)) : null,
      j.close_date ? el("span", { class: "chip" + (daysLeft(j.close_date) <= 3 ? " urgent" : "") }, "截止: " + fmtDate(j.close_date)) : null,
      j.source ? el("span", { class: "chip muted" }, "来源: " + j.source) : null
    ),
    j.url ? el("div", { class: "mt-12" },
      el("a", { href: j.url, target: "_blank", class: "btn sm" }, "🔗 查看官网投递页 ↗")
    ) : null
  );

  if (j.description) {
    body.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "📋 岗位描述"),
      el("div", { class: "detail-content" }, j.description)
    ));
  }
  if (j.requirements) {
    body.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "✅ 岗位要求"),
      el("div", { class: "detail-content" }, j.requirements)
    ));
  }

  body.appendChild(el("div", { class: "detail-section" },
    el("h5", { class: "detail-section-title" }, "🎯 匹配分析"),
    el("div", { id: "match-result", class: "empty-mini" }, "点击下方按钮生成匹配分析")
  ));

  showModal(j.company + " · " + j.title, body, [
    el("button", { class: "btn", onclick: function() { analyzeJob(j.id, false); } }, "⚡ 快速匹配"),
    el("button", { class: "btn", onclick: function() { analyzeJob(j.id, true); } }, "🤖 AI分析"),
    el("button", { class: "btn primary", onclick: function() { quickApply(j); } }, "📝 记录投递"),
    j.url ? el("button", { class: "btn", onclick: function() { fetchJD(j.id); } }, "📥 抓取JD") : null,
    el("button", { class: "btn", onclick: closeModal }, "关闭")
  ]);
}

async function analyzeJob(id, useAI) {
  var box = document.getElementById("match-result");
  if (!box) return;
  box.innerHTML = '<div class="loading">' + (useAI ? "AI 深度分析中…" : "快速匹配中…") + '</div>';
  try {
    var r = await API.get("/api/ai/match/job/" + id + "?use_ai=" + useAI);
    box.innerHTML = "";
    if (r.error) { box.innerHTML = '<div class="tag danger">' + r.error + '</div>'; return; }
    var scoreColor = r.score >= 70 ? "var(--green)" : r.score >= 40 ? "var(--orange)" : "var(--red)";
    box.appendChild(el("div", { class: "match-result-header" },
      el("div", { class: "match-score-ring", style: "border-color:" + scoreColor },
        el("span", { class: "match-score-num" }, r.score)
      ),
      el("div", {},
        el("div", { class: "bold" }, "匹配度 " + r.score + " 分"),
        r.summary ? el("div", { class: "text-sm muted mt-4" }, r.summary) : null
      )
    ));
    if (r.match_points && r.match_points.length) {
      box.appendChild(el("div", { class: "mt-12" },
        el("h5", {}, "✅ 匹配项"),
        ...r.match_points.map(function(p) { return el("div", { class: "text-sm" }, "· " + p); })
      ));
    }
    if (r.gaps && r.gaps.length) {
      box.appendChild(el("div", { class: "mt-12" },
        el("h5", {}, "⚠️ 差距"),
        ...r.gaps.map(function(p) { return el("div", { class: "text-sm" }, "· " + p); })
      ));
    }
  } catch(e) {
    box.innerHTML = '<div class="tag danger">分析失败: ' + e.message + '</div>';
  }
}

async function fetchJD(id) {
  toast("正在抓取 JD 内容，请稍候…");
  try {
    var r = await API.post("/api/jobs/" + id + "/fetch-jd");
    toast("JD 抓取成功！");
    // 重新获取最新的岗位数据并刷新详情弹窗
    var updated = await API.get("/api/jobs/" + id);
    closeModal();
    showJobDetail(updated);
  } catch(e) {
    var msg = (e && e.message) ? e.message : "抓取失败";
    toast("抓取失败: " + msg);
  }
}

function quickApply(j) {
  closeModal();
  var body = el("div", {},
    formRow("公司", el("input", { class: "input", id: "apply-company", value: j.company, readonly: true })),
    formRow("岗位", el("input", { class: "input", id: "apply-title", value: j.title, readonly: true })),
    formRow("投递渠道", el("input", { class: "input", id: "apply-channel", placeholder: "官网 / Boss直聘 / 内推 / 邮件" })),
    formRow("备注", el("textarea", { class: "textarea", id: "apply-notes", placeholder: "如内推码、投递时的注意事项等" }))
  );
  showModal("记录投递 · " + j.company, body, [
    el("button", { class: "btn primary", onclick: async function() {
      try {
        await API.post("/api/applications", {
          company: j.company, title: j.title, job_id: j.id,
          channel: val("apply-channel") || null,
          notes: val("apply-notes") || null
        });
        toast("已记录投递！去投递跟踪查看 →");
        closeModal();
      } catch(e) { toast("失败: " + e.message); }
    } }, "确认投递"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function toggleCompanyPass(company, jobs, meta) {
  try {
    // Pass all jobs of this company
    var allIds = jobs.map(function(j) { return j.id; });
    if (meta) allIds.push(meta.id);
    await API.post("/api/jobs/pass-company", { company: company });
    toast("已Pass " + company);
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
    toast(r.favorited ? "⭐ 已收藏，已加入待投递并同步到日历" : "已取消收藏");
    loadJobs();
  } catch(e) { toast("操作失败"); }
}

function showAddJob() {
  var body = el("div", {},
    formRow("公司名称 *", el("input", { class: "input", id: "add-j-company" })),
    formRow("岗位名称 *", el("input", { class: "input", id: "add-j-title", placeholder: "具体岗位名称，如后端开发" })),
    formRow("工作地点", el("input", { class: "input", id: "add-j-loc" })),
    formRow("薪资", el("input", { class: "input", id: "add-j-salary", placeholder: "如 15-25K" })),
    formRow("官网投递链接", el("input", { class: "input", id: "add-j-url", placeholder: "https://..." })),
    formRow("截止日期", el("input", { class: "input", id: "add-j-close", type: "date" })),
    formRow("岗位描述", el("textarea", { class: "textarea", id: "add-j-desc" })),
    formRow("岗位要求", el("textarea", { class: "textarea", id: "add-j-req" }))
  );
  showModal("手动添加岗位", body, [
    el("button", { class: "btn primary", onclick: function() { submitAddJob(); } }, "保存"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function submitAddJob() {
  var data = {
    company: val("add-j-company"), title: val("add-j-title"),
    location: val("add-j-loc") || null, salary: val("add-j-salary") || null,
    url: val("add-j-url") || null, close_date: val("add-j-close") || null,
    description: val("add-j-desc") || null, requirements: val("add-j-req") || null
  };
  if (!data.company || !data.title) { toast("请填写公司和岗位名称"); return; }
  await API.post("/api/jobs", data);
  closeModal();
  toast("岗位已添加");
  loadJobs();
}

async function runSpiderNow() {
  toast("开始抓取校招信息（可能需要1-2分钟）…");
  try {
    var r = await API.post("/api/spider/run");
    toast("抓取完成！" + (r.message || ""));
    loadJobs();
  } catch(e) { toast("抓取失败: " + e.message); }
}
