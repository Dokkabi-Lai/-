var STAGES = ["投递", "简历筛选", "笔试", "一面", "二面", "HR面", "Offer"];
var _trackFilter = "all";
var _trackGroupBy = "company"; // company or flat

window.load_track = async function() {
  var page = document.getElementById("page-track");
  page.innerHTML = "";
  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "投递跟踪"),
      el("div", { class: "page-sub muted" }, "管理投递流程，通过一个环节自动进入下一个")
    ),
    el("button", { class: "btn primary", onclick: function() { showAddApplication(); } }, "+ 新增投递")
  ));

  // 筛选栏
  page.appendChild(el("div", { class: "track-toolbar" },
    el("div", { class: "filter-tabs", id: "track-tabs" },
      el("button", { class: "tab-btn active", "data-filter": "all", onclick: function() { setTrackFilter("all"); } }, "全部"),
      el("button", { class: "tab-btn", "data-filter": "active", onclick: function() { setTrackFilter("active"); } }, "进行中"),
      el("button", { class: "tab-btn", "data-filter": "rejected", onclick: function() { setTrackFilter("rejected"); } }, "已淘汰"),
      el("button", { class: "tab-btn", "data-filter": "completed", onclick: function() { setTrackFilter("completed"); } }, "已完成")
    ),
    el("span", { class: "muted text-sm", id: "track-count" })
  ));

  page.appendChild(el("div", { id: "track-list" }, el("div", { class: "loading" }, "加载中…")));
  loadApplications();
};

function setTrackFilter(f) {
  _trackFilter = f;
  document.querySelectorAll("#track-tabs .tab-btn").forEach(function(b) {
    b.classList.toggle("active", b.getAttribute("data-filter") === f);
  });
  loadApplications();
}

async function loadApplications() {
  var box = document.getElementById("track-list");
  if (!box) return;
  try {
    var data = await API.get("/api/applications");
    // 筛选
    if (_trackFilter === "active") data = data.filter(function(a) { return a.status !== "已淘汰" && a.status !== "已完成"; });
    if (_trackFilter === "rejected") data = data.filter(function(a) { return a.status === "已淘汰"; });
    if (_trackFilter === "completed") data = data.filter(function(a) { return a.status === "已完成"; });

    document.getElementById("track-count").textContent = data.length + " 条";
    box.innerHTML = "";
    if (!data.length) { box.appendChild(emptyState("暂无投递记录")); return; }

    // 按公司分组
    var groups = {};
    var order = [];
    data.forEach(function(app) {
      if (!groups[app.company]) { groups[app.company] = []; order.push(app.company); }
      groups[app.company].push(app);
    });

    order.forEach(function(company) {
      var apps = groups[company];
      box.appendChild(trackCompanyGroup(company, apps));
    });
  } catch(e) {
    box.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

function trackCompanyGroup(company, apps) {
  var group = el("div", { class: "track-company-group" });
  group.appendChild(el("div", { class: "track-company-header" },
    el("div", { class: "company-avatar sm" }, company.charAt(0)),
    el("div", { class: "track-company-name" }, company),
    el("span", { class: "badge" }, apps.length)
  ));
  apps.forEach(function(app) {
    group.appendChild(appCard(app));
  });
  return group;
}

function appCard(app) {
  var stages = app.stages || [];
  var isRejected = app.status === "已淘汰";
  var currentIdx = -1;
  stages.forEach(function(s, i) {
    if (s.status === "completed") currentIdx = i;
  });
  var nextIdx = currentIdx + 1;
  var nextStage = nextIdx < STAGES.length ? STAGES[nextIdx] : null;

  var card = el("div", { class: "pipeline-card" + (isRejected ? " rejected" : "") });

  // 头部：岗位信息 + 操作
  card.appendChild(el("div", { class: "pipeline-header" },
    el("div", { class: "pipeline-info" },
      el("div", {},
        el("div", { class: "pipeline-title" }, app.title),
        el("div", { class: "pipeline-meta" },
          app.channel ? el("span", { class: "chip sm" }, app.channel) : null,
          el("span", { class: "text-sm muted" }, "投递于 " + (app.applied_at || "").slice(0, 10)),
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
    else if (idx === nextIdx && !isRejected) statusClass = "current";
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
      stageData.scheduled_at ? el("div", { class: "stage-time" }, stageData.scheduled_at.slice(5, 16).replace("T", " ")) : null,
      stageData.feedback ? el("div", { class: "stage-has-review" }, "📝") : null
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
    loadApplications();
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
      var note = val("offer-note");
      if (note) {
        try {
          await API.patch("/api/applications/" + app.id + "/stage/Offer", { feedback: note });
        } catch(e) {}
      }
      closeModal();
      toast("🎊 已存入Offer库！");
      loadApplications();
    } }, "🎊 存入Offer库"),
    el("button", { class: "btn", onclick: closeModal }, "稍后填写")
  ]);
}

function rejectAtStage(app, stage) {
  // 直接淘汰，无需弹窗
  API.post("/api/applications/" + app.id + "/reject", { stage: stage }).then(function() {
    toast("❌ 已标记在「" + stage + "」淘汰");
    loadApplications();
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
      await API.post("/api/applications/" + app.id + "/reject", { stage: val("reject-stage") });
      toast("已标记淘汰");
      closeModal();
      loadApplications();
    } }, "确认淘汰"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function restoreApp(id) {
  await API.post("/api/applications/" + id + "/restore");
  toast("♻️ 已恢复");
  loadApplications();
}

function showStageEditor(app, stageName, stageData) {
  var stageIdx = STAGES.indexOf(stageName);
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
    formRow("安排时间（同步日历）", el("input", { class: "input", id: "se-time", type: "datetime-local", value: (stageData.scheduled_at || "").slice(0, 16) })),
    formRow("形式", el("select", { class: "select", id: "se-form" },
      el("option", { value: "" }, "请选择"),
      el("option", { value: "现场", selected: stageData.form === "现场" ? true : undefined }, "现场"),
      el("option", { value: "线上", selected: stageData.form === "线上" ? true : undefined }, "线上"),
      el("option", { value: "电话", selected: stageData.form === "电话" ? true : undefined }, "电话")
    )),
    formRow("地点/会议链接", el("input", { class: "input", id: "se-loc", value: stageData.location || "", placeholder: "如: 腾讯大厦B1 / 腾讯会议xxx" })),
    formRow("备注", el("textarea", { class: "textarea", id: "se-notes", placeholder: "面试官信息、准备材料等" }, stageData.notes || "")),
    el("div", { class: "form-divider" }),
    el("h4", { class: "mt-16 mb-8" }, "📝 面试反馈 / 复盘"),
    el("textarea", { class: "textarea lg", id: "se-feedback", placeholder: "面试题目、自己的表现、改进点、面试官反馈等...\n\n写下来帮助后续面试复盘！" }, stageData.feedback || "")
  );

  var buttons = [
    el("button", { class: "btn primary", onclick: async function() {
      try {
        await API.patch("/api/applications/" + app.id + "/stage/" + encodeURIComponent(stageName), {
          status: val("se-status"),
          scheduled_at: val("se-time") || null,
          form: val("se-form") || null,
          location: val("se-loc") || null,
          notes: val("se-notes") || null,
          feedback: val("se-feedback") || null
        });
        toast("已保存");
        closeModal();
        loadApplications();
      } catch(e) { toast("保存失败: " + e.message); }
    } }, "保存")
  ];
  // 回退按钮：如果当前阶段已经过了，允许回退到这个阶段
  if (stageData.status === "completed" || stageIdx < STAGES.indexOf(app.current_stage)) {
    buttons.push(el("button", { class: "btn warn", onclick: async function() {
      try {
        await API.post("/api/applications/" + app.id + "/rollback", { stage: stageName });
        toast("已回退到「" + stageName + "」");
        closeModal();
        loadApplications();
      } catch(e) { toast("回退失败: " + e.message); }
    } }, "⏪ 回退到此"));
  }
  buttons.push(el("button", { class: "btn", onclick: closeModal }, "取消"));

  showModal("编辑阶段 · " + stageName, body, buttons);
}

function editApplication(app) {
  var body = el("div", {},
    formRow("公司", el("input", { class: "input", id: "ea-company", value: app.company })),
    formRow("岗位", el("input", { class: "input", id: "ea-title", value: app.title })),
    formRow("投递渠道", el("input", { class: "input", id: "ea-channel", value: app.channel || "" })),
    formRow("备注", el("textarea", { class: "textarea", id: "ea-notes" }, app.notes || ""))
  );
  showModal("编辑投递 · " + app.company, body, [
    el("button", { class: "btn primary", onclick: async function() {
      await API.patch("/api/applications/" + app.id, {
        company: val("ea-company"), title: val("ea-title"),
        channel: val("ea-channel") || null, notes: val("ea-notes") || null
      });
      toast("已更新"); closeModal(); loadApplications();
    } }, "保存"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function deleteApplication(id) {
  if (!confirm("确认删除此投递记录？所有阶段和复盘数据都将丢失。")) return;
  await API.del("/api/applications/" + id);
  toast("已删除");
  loadApplications();
}

function showAddApplication() {
  var body = el("div", {},
    formRow("公司 *", el("input", { class: "input", id: "na-company" })),
    formRow("岗位 *", el("input", { class: "input", id: "na-title" })),
    formRow("投递渠道", el("input", { class: "input", id: "na-channel", placeholder: "官网 / Boss直聘 / 内推" })),
    formRow("备注", el("textarea", { class: "textarea", id: "na-notes" }))
  );
  showModal("新增投递", body, [
    el("button", { class: "btn primary", onclick: async function() {
      var company = val("na-company"), title = val("na-title");
      if (!company || !title) { toast("请填写公司和岗位"); return; }
      await API.post("/api/applications", {
        company: company, title: title,
        channel: val("na-channel") || null, notes: val("na-notes") || null
      });
      toast("已添加"); closeModal(); loadApplications();
    } }, "添加"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}
