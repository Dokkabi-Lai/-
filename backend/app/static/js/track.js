var STAGES = ["投递", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer"];
var _trackFilter = "all";
var _trackPagerIndex = 0;
var _trackPagerData = [];
var _trackQuery = "";
var _trackApplications = null;

window.load_track = async function() {
  var page = document.getElementById("page-track");
  page.innerHTML = "";
  if (window._trackFilterPending) {
    _trackFilter = window._trackFilterPending;
    window._trackFilterPending = null;
  }
  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "流程跟踪"),
      el("div", { class: "page-sub muted" }, "流程、Offer 与进度都在这里")
    ),
    el("button", { class: "btn primary", onclick: function() { showAddApplication(); } }, "+ 新增投递")
  ));

  page.appendChild(el("div", { class: "track-toolbar" },
    el("div", { class: "filter-tabs scroll-tabs", id: "track-tabs" },
      el("button", { class: "tab-btn" + (_trackFilter === "all" ? " active" : ""), "data-filter": "all", onclick: function() { setTrackFilter("all"); } }, "全部"),
      el("button", { class: "tab-btn" + (_trackFilter === "active" ? " active" : ""), "data-filter": "active", onclick: function() { setTrackFilter("active"); } }, "进行中"),
      el("button", { class: "tab-btn rejected-filter" + (_trackFilter === "rejected" ? " active" : ""), "data-filter": "rejected", onclick: function() { setTrackFilter("rejected"); } }, "已淘汰"),
      el("button", { class: "tab-btn" + (_trackFilter === "offers" ? " active" : ""), "data-filter": "offers", onclick: function() { setTrackFilter("offers"); } }, "Offer")
    ),
    el("div", { class: "track-search" },
      el("span", { class: "track-search-icon", "aria-hidden": "true" }, "⌕"),
      el("input", {
        class: "input track-search-input", id: "track-search", type: "search",
        placeholder: "搜索公司、岗位或阶段", value: _trackQuery,
        autocomplete: "off", "aria-label": "搜索流程",
        oninput: function(event) {
          _trackQuery = event.target.value;
          _trackPagerIndex = 0;
          if (_trackApplications) renderTrackApplications(_trackApplications);
        }
      })
    ),
    el("span", { class: "muted text-sm", id: "track-count" })
  ));

  page.appendChild(el("div", { id: "track-list" }, el("div", { class: "loading" }, "加载中…")));
  loadApplications();
};

function setTrackFilter(f) {
  _trackFilter = f;
  _trackPagerIndex = 0;
  document.querySelectorAll("#track-tabs .tab-btn").forEach(function(b) {
    b.classList.toggle("active", b.getAttribute("data-filter") === f);
  });
  if (_trackApplications) renderTrackApplications(_trackApplications);
  else loadApplications();
}

async function loadApplications() {
  var box = document.getElementById("track-list");
  if (!box) return;
  try {
    _trackApplications = sortTrackApplications(await API.get("/api/applications"));
    renderTrackApplications(_trackApplications);
  } catch(e) {
    box.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

// 保存操作的接口会返回完整投递记录。直接更新本地卡片，避免每次操作后
// 再请求整份投递列表，尤其适合远程 PostgreSQL 和手机网络。
function syncTrackApplication(updated) {
  if (!updated) return;
  if (!_trackApplications) {
    loadApplications();
    return;
  }
  var index = _trackApplications.findIndex(function(item) {
    return String(item.id) === String(updated.id);
  });
  if (index >= 0) _trackApplications[index] = updated;
  else _trackApplications.unshift(updated);
  sortTrackApplications(_trackApplications);
  window._trackFocusId = updated.id;
  renderTrackApplications(_trackApplications);
  markApplicationViewsStale();
}

function removeTrackApplication(appId) {
  if (_trackApplications) {
    _trackApplications = _trackApplications.filter(function(item) {
      return String(item.id) !== String(appId);
    });
    renderTrackApplications(_trackApplications);
  }
  markApplicationViewsStale();
}

function markApplicationViewsStale() {
  if (typeof _renderedPages === "undefined") return;
  ["home", "calendar", "profile", "offers"].forEach(function(page) {
    _renderedPages[page] = false;
  });
}

function trackTimeValue(value) {
  var time = value ? Date.parse(value) : NaN;
  return Number.isFinite(time) ? time : 0;
}

function sortTrackApplications(items) {
  return (items || []).sort(function(a, b) {
    return trackTimeValue(b.applied_at) - trackTimeValue(a.applied_at)
      || trackTimeValue(b.updated_at) - trackTimeValue(a.updated_at)
      || Number(b.id || 0) - Number(a.id || 0);
  });
}

function renderTrackApplications(allData) {
  var box = document.getElementById("track-list");
  if (!box) return;
  var data = sortTrackApplications((allData || []).slice());
    if (_trackFilter === "active") data = data.filter(function(a) { return a.status !== "已淘汰" && a.status !== "已完成"; });
    if (_trackFilter === "rejected") data = data.filter(function(a) { return a.status === "已淘汰"; });
    if (_trackFilter === "completed") data = data.filter(function(a) { return a.status === "已完成"; });
    if (_trackFilter === "offers") data = data.filter(function(a) { return a.status === "已完成"; });

    var query = (_trackQuery || "").trim().toLowerCase();
    if (query) {
      data = data.filter(function(app) {
        var stageText = (app.stages || []).map(function(stage) {
          return [stage.stage, stage.status, stage.notes].filter(Boolean).join(" ");
        }).join(" ");
        return [app.company, app.title, app.channel, app.status, app.current_stage, app.rejected_stage, app.notes, stageText]
          .filter(Boolean).join(" ").toLowerCase().includes(query);
      });
    }

    document.getElementById("track-count").textContent = data.length + " 条";
    box.innerHTML = "";
    if (!data.length) {
      var emptyText = query ? "没有匹配的岗位，换个关键词试试"
        : (_trackFilter === "offers" ? "还没有拿到 Offer，继续加油！"
          : (_trackFilter === "rejected" ? "暂时没有已淘汰的岗位" : "暂无投递记录"));
      box.appendChild(emptyState(emptyText));
      return;
    }

    var focusId = window._trackFocusId;
    window._trackFocusId = null;
    if (focusId) {
      var focusIndex = data.findIndex(function(app) { return String(app.id) === String(focusId); });
      if (focusIndex >= 0) _trackPagerIndex = focusIndex;
    }

    if (_trackFilter === "offers") {
      box.appendChild(el("div", { class: "offer-stats" },
        el("div", { class: "offer-stat-card" },
          el("div", { class: "offer-stat-num" }, data.length),
          el("div", { class: "offer-stat-label" }, "Offer 数")
        )
      ));
      box.appendChild(renderTrackPager(data, function(app) {
        return typeof offerCard === "function" ? offerCard(app) : appCard(app);
      }));
      return;
    }

    box.appendChild(renderTrackPager(data, appCard));
}

function renderTrackPager(data, renderer) {
  _trackPagerData = data || [];
  if (_trackPagerIndex < 0 || _trackPagerIndex >= _trackPagerData.length) _trackPagerIndex = 0;

  var pager = el("section", { class: "track-pager" });
  var identity = el("div", { class: "track-pager-identity" });
  var counter = el("span", { class: "track-pager-counter" });
  var cardWrap = el("div", { class: "track-pager-card track-pager-swipe-surface", "aria-live": "polite" });
  var slider = el("input", {
    class: "track-pager-slider", type: "range", min: "0", max: String(Math.max(0, _trackPagerData.length - 1)),
    value: String(_trackPagerIndex), step: "1", "aria-label": "滑动选择岗位",
    oninput: function(event) {
      var target = Number(event.target.value);
      var direction = target > _trackPagerIndex ? "next" : target < _trackPagerIndex ? "prev" : "";
      _trackPagerIndex = target;
      paint(direction);
    }
  });
  slider.disabled = _trackPagerData.length <= 1;
  var prev = el("button", { class: "btn sm track-pager-btn", type: "button", "aria-label": "上一个岗位", onclick: function() { move(-1); } }, "← 上一个");
  var next = el("button", { class: "btn sm primary track-pager-btn", type: "button", "aria-label": "下一个岗位", onclick: function() { move(1); } }, "下一个 →");

  pager.appendChild(el("div", { class: "track-pager-head" },
    el("div", {},
      el("div", { class: "section-kicker" }, "ONE ROLE AT A TIME"),
      identity
    ),
    counter
  ));
  pager.appendChild(cardWrap);
  pager.appendChild(el("div", { class: "track-pager-foot" },
    prev,
    el("div", { class: "track-pager-slider-wrap" },
      el("span", { class: "track-pager-slider-hint" }, "左右滑动查看"),
      slider
    ),
    next
  ));

  var swipeStartX = 0;
  var swipeStartY = 0;
  var swipeActive = false;
  var suppressClickUntil = 0;
  cardWrap.addEventListener("pointerdown", function(event) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (event.target && event.target.closest && event.target.closest("button,a,input,textarea,select")) return;
    swipeStartX = event.clientX;
    swipeStartY = event.clientY;
    swipeActive = true;
    cardWrap.classList.add("is-dragging");
    if (cardWrap.setPointerCapture) cardWrap.setPointerCapture(event.pointerId);
  });
  cardWrap.addEventListener("pointerup", function(event) {
    if (!swipeActive) return;
    var dx = event.clientX - swipeStartX;
    var dy = event.clientY - swipeStartY;
    swipeActive = false;
    cardWrap.classList.remove("is-dragging");
    if (Math.abs(dx) >= 48 && Math.abs(dx) > Math.abs(dy) * 1.15) {
      suppressClickUntil = Date.now() + 350;
      move(dx < 0 ? 1 : -1);
    }
  });
  cardWrap.addEventListener("pointercancel", function() {
    swipeActive = false;
    cardWrap.classList.remove("is-dragging");
  });
  cardWrap.addEventListener("click", function(event) {
    if (Date.now() < suppressClickUntil) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  function move(step) {
    var target = _trackPagerIndex + step;
    if (target < 0 || target >= _trackPagerData.length) return;
    _trackPagerIndex = target;
    paint(step > 0 ? "next" : "prev");
  }

  function paint(direction) {
    var app = _trackPagerData[_trackPagerIndex];
    if (!app) return;
    identity.textContent = (app.company || "未命名公司") + " · " + (app.title || "未命名岗位");
    counter.textContent = "第 " + (_trackPagerIndex + 1) + " / " + _trackPagerData.length + " 个岗位";
    slider.value = String(_trackPagerIndex);
    slider.style.setProperty(
      "--pager-progress",
      (_trackPagerData.length <= 1 ? 100 : _trackPagerIndex / (_trackPagerData.length - 1) * 100) + "%"
    );
    slider.setAttribute("aria-valuetext", "第 " + (_trackPagerIndex + 1) + " / " + _trackPagerData.length + " 个岗位");
    prev.disabled = _trackPagerIndex === 0;
    next.disabled = _trackPagerIndex === _trackPagerData.length - 1;
    cardWrap.innerHTML = "";
    var card = renderer(app);
    if (card) cardWrap.appendChild(card);
    cardWrap.classList.remove("pager-swap-next", "pager-swap-prev");
    if (direction) {
      void cardWrap.offsetWidth;
      cardWrap.classList.add(direction === "next" ? "pager-swap-next" : "pager-swap-prev");
    }

  }

  // 支持按钮、拖动滑块和手机左右手势三种切换方式。
  paint();
  return pager;
}

function appCard(app) {
  var stages = app.stages || [];
  var isRejected = app.status === "已淘汰";
  var currentIdx = -1;
  var explicitCurrentIdx = -1;
  stages.forEach(function(s, i) {
    if (s.status === "completed") currentIdx = i;
    if (s.status === "current") explicitCurrentIdx = i;
  });
  var nextIdx = explicitCurrentIdx >= 0 ? explicitCurrentIdx : currentIdx + 1;
  var nextStage = nextIdx < STAGES.length ? STAGES[nextIdx] : null;

  var card = el("div", { class: "pipeline-card" + (isRejected ? " rejected" : ""), "data-app-id": app.id });

  // 头部：岗位信息 + 操作
  card.appendChild(el("div", { class: "pipeline-header" },
    el("div", { class: "pipeline-info" },
      el("div", { class: "company-avatar sm pipeline-avatar" }, (app.company || "?").charAt(0)),
      el("div", {},
        el("div", { class: "pipeline-company" }, app.company),
        el("div", { class: "pipeline-title" }, app.title),
        el("div", { class: "pipeline-meta" },
          app.channel ? el("span", { class: "chip sm" }, app.channel) : null,
          el("span", { class: "text-sm muted", style: "cursor:pointer", title: "点击修改投递时间", onclick: function(e) { e.stopPropagation(); editApplication(app); } }, "投递于 " + (app.applied_at || "").slice(0, 10)),
          app.job_url ? el("a", { class: "pipeline-job-link", href: app.job_url, target: "_blank", rel: "noopener noreferrer", onclick: function(e) { e.stopPropagation(); } }, "岗位链接 ↗") : null,
          isRejected ? el("span", { class: "chip sm rejected-chip" }, "❌ " + (app.rejected_stage || "") + "淘汰") : null
        )
      )
    ),
    el("div", { class: "btn-group" },
      el("button", { class: "btn sm", onclick: function(e) { e.stopPropagation(); editApplication(app); } }, "✏️"),
      el("button", { class: "btn sm danger", onclick: function(e) { e.stopPropagation(); deleteApplication(app.id); } }, "🗑️")
    )
  ));

  // 流程管道 - 带一键操作
  var pipeline = el("div", { class: "pipeline-stages" });
  STAGES.forEach(function(stageName, idx) {
    var stageData = stages.find(function(s) { return s.stage === stageName; }) || {};
    var statusClass = "";
    if (isRejected && stageName === app.rejected_stage) statusClass = "rejected";
    else if (stageData.status === "completed") statusClass = "completed";
    else if ((stageData.status === "current" || idx === nextIdx) && !isRejected) statusClass = "current";
    else if (stageData.status === "skipped") statusClass = "skipped";

    var statusText = "";
    if (statusClass === "completed") statusText = "已通过";
    else if (statusClass === "rejected") statusText = "未通过";
    else if (statusClass === "current") statusText = "进行中";
    else if (statusClass === "skipped") statusText = "未通过";

    var stageEl = el("div", { class: "stage-item " + statusClass },
      el("div", { class: "stage-dot " + statusClass }),
      el("div", { class: "stage-label " + statusClass }, stageName),
      statusText ? el("div", { class: "stage-status-text " + statusClass }, statusText) : null,
      stageScheduleLabel(stageData) ? el("div", { class: "stage-time" }, stageScheduleLabel(stageData)) : null
    );
    stageEl.onclick = function(e) { e.stopPropagation(); showStageEditor(app, stageName, stageData); };
    pipeline.appendChild(stageEl);
  });
  card.appendChild(pipeline);

  // 底部操作栏 - 核心交互：通过/淘汰
  var footer = el("div", { class: "pipeline-footer" });
  if (!isRejected && nextStage) {
    var passBtnText = nextStage === "Offer" ? "✅ 拿到Offer" : "✅ 通过";
    footer.appendChild(el("div", { class: "stage-action-bar" },
      el("span", { class: "text-sm" }, "当前: "),
      el("span", { class: "tag primary" }, nextStage),
      el("button", { class: "btn sm ok", onclick: function(e) { e.stopPropagation(); advanceStage(app.id); } }, passBtnText),
      el("button", { class: "btn sm danger", onclick: function(e) { e.stopPropagation(); rejectAtStage(app, nextStage); } }, "❌ 淘汰")
    ));
  } else if (isRejected) {
    footer.appendChild(el("div", { class: "stage-action-bar" },
      el("span", { class: "muted text-sm" }, "流程终止于「" + (app.rejected_stage || "") + "」"),
      el("button", { class: "btn sm", onclick: function(e) { e.stopPropagation(); restoreApp(app.id); } }, "♻️ 恢复")
    ));
  } else {
    footer.appendChild(el("span", { class: "tag ok" }, "🎉 流程已完成"));
  }
  if (app.notes) {
    footer.appendChild(el("div", { class: "pipeline-notes muted text-sm" }, "📝 " + app.notes));
  }
  card.appendChild(footer);

  return card;
}

async function advanceStage(appId) {
  try {
    var r = await API.post("/api/applications/" + appId + "/advance");
    // 检查是否拿到了offer
    if (r.status === "已完成" && r.current_stage === "Offer") {
      showOfferCelebration(r);
    } else {
      toast("✅ 已通过，进入下一环节");
    }
    syncTrackApplication(r);
  } catch(e) { toast("操作失败: " + e.message); }
}

function showOfferCelebration(app) {
  var body = el("div", { class: "celebration" },
    el("div", { class: "celebration-icon" }, "🎉"),
    el("h2", { class: "celebration-title" }, "恭喜你拿到Offer！"),
    el("div", { class: "celebration-company" }, app.company + " · " + app.title),
    el("p", { class: "muted mt-12" }, "你的努力得到了回报！可以去「我的Offer」页面查看详情。"),
    el("div", { class: "form-divider" }),
    formRow("Offer备注（可选）", el("textarea", { class: "textarea", id: "offer-note", placeholder: "薪资、入职时间、特别条件等..." }))
  );
  showModal("🎉 恭喜！", body, [
    el("button", { class: "btn primary", onclick: async function() {
      var updated = app;
      var note = val("offer-note");
      if (note) {
        try {
          updated = await API.patch("/api/applications/" + app.id + "/stage/Offer", { notes: note });
        } catch(e) {}
      }
      closeModal();
      toast("🎊 已存入Offer库！");
      syncTrackApplication(updated);
    } }, "🎊 存入Offer库"),
    el("button", { class: "btn", onclick: closeModal }, "稍后填写")
  ]);
}

function rejectAtStage(app, stage) {
  // 直接淘汰，无需弹窗
  API.post("/api/applications/" + app.id + "/reject", { stage: stage }).then(function(updated) {
    toast("❌ 已标记在「" + stage + "」淘汰");
    syncTrackApplication(updated);
  }).catch(function(e) { toast("操作失败"); });
}

function showRejectDialog(app) {
  var body = el("div", {},
    el("p", {}, "标记「" + app.company + " · " + app.title + "」为已淘汰"),
    formRow("在哪个环节被淘汰", el("select", { class: "select", id: "reject-stage" },
      ...STAGES.map(function(s) {
        return el("option", { value: s, selected: s === app.current_stage ? true : undefined }, s);
      })
    ))
  );
  showModal("标记淘汰", body, [
    el("button", { class: "btn danger", onclick: async function() {
      var updated = await API.post("/api/applications/" + app.id + "/reject", { stage: val("reject-stage") });
      toast("已标记淘汰");
      closeModal();
      syncTrackApplication(updated);
    } }, "确认淘汰"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function restoreApp(id) {
  var updated = await API.post("/api/applications/" + id + "/restore");
  toast("♻️ 已恢复");
  syncTrackApplication(updated);
}

function showStageEditor(app, stageName, stageData) {
  var stageIdx = STAGES.indexOf(stageName);
  var isExam = stageName === "笔试";
  var scheduleType = stageData.schedule_type || (stageData.deadline_at ? "deadline" : "exact");
  var exactTimeInput = el("input", {
    class: "input", id: "se-time", type: "datetime-local",
    value: (stageData.scheduled_at || "").slice(0, 16)
  });
  var exactTimeRow = formRow(isExam ? "固定开始时间" : "安排时间（同步日历）", exactTimeInput);
  exactTimeRow.id = "se-exact-time-row";
  var deadlineTimeInput = el("input", {
    class: "input", id: "se-deadline", type: "datetime-local",
    value: (stageData.deadline_at || "").slice(0, 16)
  });
  var deadlineTimeRow = formRow("最晚完成时间", deadlineTimeInput);
  deadlineTimeRow.id = "se-deadline-time-row";
  var scheduleTypeSelect = el("select", { class: "select", id: "se-schedule-type" },
    el("option", { value: "exact", selected: scheduleType === "exact" ? true : undefined }, "固定时间 · 到点参加"),
    el("option", { value: "deadline", selected: scheduleType === "deadline" ? true : undefined }, "截止时间 · 在此之前完成")
  );
  var scheduleModeRow = formRow("笔试时间类型", scheduleTypeSelect);

  var timeFields = isExam ? [scheduleModeRow, exactTimeRow, deadlineTimeRow] : [exactTimeRow];
  var body = el("div", {},
    el("div", { class: "stage-editor-header" },
      el("div", { class: "company-avatar sm" }, app.company.charAt(0)),
      el("div", {},
        el("div", { class: "bold" }, app.company + " · " + app.title),
        el("div", { class: "muted text-sm" }, "阶段: " + stageName)
      )
    ),
    formRow("状态", el("select", { class: "select", id: "se-status" },
      el("option", { value: "pending", selected: stageData.status === "pending" ? true : undefined }, "待进行"),
      el("option", { value: "current", selected: stageData.status === "current" ? true : undefined }, "进行中"),
      el("option", { value: "completed", selected: stageData.status === "completed" ? true : undefined }, "已通过"),
      el("option", { value: "skipped", selected: stageData.status === "skipped" ? true : undefined }, "未通过/跳过")
    )),
    ...timeFields,
    formRow("形式", el("select", { class: "select", id: "se-form" },
      el("option", { value: "" }, "请选择"),
      el("option", { value: "现场", selected: stageData.form === "现场" ? true : undefined }, "现场"),
      el("option", { value: "线上", selected: stageData.form === "线上" ? true : undefined }, "线上"),
      el("option", { value: "电话", selected: stageData.form === "电话" ? true : undefined }, "电话")
    )),
    formRow("地点/会议链接", el("input", { class: "input", id: "se-loc", value: stageData.location || "", placeholder: "如: 腾讯大厦B1 / 腾讯会议xxx" })),
    formRow("备注", el("textarea", { class: "textarea", id: "se-notes", placeholder: "准备材料、注意事项等" }, stageData.notes || ""))
  );

  function syncExamTimeFields() {
    if (!isExam) return;
    var mode = scheduleTypeSelect.value || "exact";
    exactTimeRow.style.display = mode === "exact" ? "" : "none";
    deadlineTimeRow.style.display = mode === "deadline" ? "" : "none";
  }
  if (isExam) {
    scheduleTypeSelect.addEventListener("change", syncExamTimeFields);
    syncExamTimeFields();
  }

  var buttons = [
    el("button", { class: "btn primary", onclick: async function() {
      try {
        var updated = await API.patch("/api/applications/" + app.id + "/stage/" + encodeURIComponent(stageName), {
          status: val("se-status"),
          schedule_type: isExam ? (val("se-schedule-type") || "exact") : "exact",
          scheduled_at: isExam && val("se-schedule-type") === "deadline" ? null : (val("se-time") || null),
          deadline_at: isExam && val("se-schedule-type") === "deadline" ? (val("se-deadline") || null) : null,
          form: val("se-form") || null,
          location: val("se-loc") || null,
          notes: val("se-notes") || null
        });
        toast("已保存");
        closeModal();
        syncTrackApplication(updated);
      } catch(e) { toast("保存失败: " + e.message); }
    } }, "保存")
  ];
  // 回退按钮：如果当前阶段已经过了，允许回退到这个阶段
  if (stageData.status === "completed" || stageIdx < STAGES.indexOf(app.current_stage)) {
    buttons.push(el("button", { class: "btn warn", onclick: async function() {
      try {
        var updated = await API.post("/api/applications/" + app.id + "/rollback", { stage: stageName });
        toast("已回退到「" + stageName + "」");
        closeModal();
        syncTrackApplication(updated);
      } catch(e) { toast("回退失败: " + e.message); }
    } }, "⏪ 回退到此"));
  }
  buttons.push(el("button", { class: "btn", onclick: closeModal }, "取消"));

  showModal("编辑阶段 · " + stageName, body, buttons);
}

function editApplication(app) {
  var appliedVal = (app.applied_at || "").slice(0, 16);
  var body = el("div", {},
    formRow("公司", el("input", { class: "input", id: "ea-company", value: app.company })),
    formRow("岗位", el("input", { class: "input", id: "ea-title", value: app.title })),
    formRow("投递时间", el("input", { class: "input", id: "ea-applied", type: "datetime-local", value: appliedVal })),
    formRow("投递渠道", el("input", { class: "input", id: "ea-channel", value: app.channel || "" })),
    formRow("备注", el("textarea", { class: "textarea", id: "ea-notes" }, app.notes || ""))
  );
  showModal("编辑投递 · " + app.company, body, [
    el("button", { class: "btn primary", onclick: async function() {
      var updated = await API.patch("/api/applications/" + app.id, {
        company: val("ea-company"), title: val("ea-title"),
        applied_at: val("ea-applied") || null,
        channel: val("ea-channel") || null, notes: val("ea-notes") || null
      });
      toast("已更新"); closeModal(); syncTrackApplication(updated);
    } }, "保存"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function deleteApplication(id) {
  if (!confirm("确认删除此投递记录？所有阶段记录都将丢失。")) return;
  await API.del("/api/applications/" + id);
  toast("已删除");
  removeTrackApplication(id);
}

function showAddApplication() {
  var body = el("div", {},
    formRow("公司 *", el("input", { class: "input", id: "na-company" })),
    formRow("岗位 *", el("input", { class: "input", id: "na-title" })),
    formRow("投递渠道", el("input", { class: "input", id: "na-channel", placeholder: "官网 / Boss直聘 / 内推" })),
    formRow("投递时间", el("input", { class: "input", id: "na-applied", type: "datetime-local" })),
    formRow("备注", el("textarea", { class: "textarea", id: "na-notes" }))
  );
  showModal("新增投递", body, [
    el("button", { class: "btn primary", onclick: async function() {
      var company = val("na-company"), title = val("na-title");
      if (!company || !title) { toast("请填写公司和岗位"); return; }
      var created = await API.post("/api/applications", {
        company: company, title: title,
        channel: val("na-channel") || null,
        applied_at: val("na-applied") || null,
        notes: val("na-notes") || null
      });
      toast("已添加"); closeModal(); syncTrackApplication(created);
    } }, "添加"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}
