window.load_home = async function() {
  var page = document.getElementById("page-home");
  page.innerHTML = '<div class="home-loading"><span class="loading-orb"></span><span>正在整理今天的重点…</span></div>';
  try {
    var data = await API.get("/api/home");
    renderHome(data || {});

    var later = window.requestIdleCallback || function(fn) { setTimeout(fn, 500); };
    later(function() {
      if (typeof loadDashboard === "function") loadDashboard();
    });
  } catch(e) {
    page.innerHTML = "";
    page.appendChild(el("div", { class: "card error-card" }, "加载失败：" + e.message));
  }
};

function renderHome(data) {
  var page = document.getElementById("page-home");
  var stats = data.stats || {};
  var notifications = data.notifications || [];
  var nickname = (currentUser && currentUser.nickname) || "求职人";
  var hour = new Date().getHours();
  var greeting = hour < 12 ? "早上好" : hour < 18 ? "下午好" : "晚上好";

  page.innerHTML = "";
  var shell = el("div", { class: "home-shell" });
  shell.appendChild(el("section", { class: "home-hero" },
    el("div", { class: "home-hero-copy" },
      el("div", { class: "home-hero-kicker" },
        el("span", {}, "MY JOB DESK"),
        el("span", { class: "home-hero-date" }, homeDateLabel())
      ),
      el("h1", {}, greeting + "，" + nickname),
      el("p", {}, "先处理最紧急的一件事，剩下的交给你的节奏。"),
      el("div", { class: "home-hero-actions" },
        el("button", { class: "btn primary hero-primary", onclick: function() {
          if (typeof showAddApplication === "function") showAddApplication();
          else showPage("track");
        } }, "+ 记录投递"),
        el("button", { class: "btn ghost hero-secondary", onclick: function() { showPage("jobs"); } }, "探索岗位 →")
      )
    ),
    el("div", { class: "home-hero-mark", "aria-hidden": "true" },
      el("span", { class: "hero-mark-line" }),
      el("span", { class: "hero-mark-text" }, "秋")
    )
  ));

  shell.appendChild(el("div", { class: "home-focus-grid" },
    renderDeadlinePushes(notifications),
    renderTodaySchedules(data.today_schedules || []),
    renderTodoCard(data.todos || [])
  ));

  shell.appendChild(el("div", { class: "home-stats" },
    homeStat("!", notifications.length, "待处理提醒", notifications.length ? "alert" : "calm", function() {
      var pushCard = document.querySelector(".push-card");
      if (pushCard) pushCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }),
    homeStat("↗", stats.in_progress_count || 0, "进行中", "accent", function() { showPage("track"); }),
    homeStat("◷", stats.schedule_count || 0, "今日安排", "teal", function() { showPage("calendar"); }),
    homeStat("✦", stats.offer_count || 0, "Offer", "green", function() {
      window._trackFilterPending = "offers";
      showPage("track");
    }),
    homeStat("#", stats.total_apps || 0, "总投递", "violet", function() { showPage("track"); })
  ));

  if (data.job_activity_today) {
    shell.appendChild(renderGroupActivity(data.job_activity_today));
  }

  var activeSection = renderActiveAppSection(data.in_progress_apps);
  var activeCollapsed = false;
  try { activeCollapsed = window.localStorage.getItem("homeActiveCollapsed") === "1"; } catch (_) {}
  activeSection.classList.toggle("is-collapsed", activeCollapsed);
  var activeToggle = el("button", {
    class: "btn ghost sm home-collapse-toggle",
    type: "button",
    "aria-expanded": String(!activeCollapsed),
    "aria-controls": "home-active-section",
    onclick: function() {
      activeCollapsed = !activeCollapsed;
      activeSection.classList.toggle("is-collapsed", activeCollapsed);
      activeToggle.setAttribute("aria-expanded", String(!activeCollapsed));
      activeToggle.textContent = activeCollapsed ? "展开" : "收起";
      try { window.localStorage.setItem("homeActiveCollapsed", activeCollapsed ? "1" : "0"); } catch (_) {}
    }
  }, activeCollapsed ? "展开" : "收起");

  shell.appendChild(el("div", { class: "home-section-head home-section-head-spaced" },
    el("div", {},
      el("div", { class: "section-kicker" }, "KEEP MOVING"),
      el("h2", { class: "section-title" }, "继续推进"),
      el("p", { class: "section-sub muted" }, "每一次状态更新，都会让下一步更清晰")
    ),
    el("div", { class: "home-section-actions" },
      activeToggle,
      el("button", { class: "btn ghost sm", onclick: function() { showPage("track"); } }, "查看全部 →")
    )
  ));

  shell.appendChild(activeSection);

  shell.appendChild(el("div", { class: "home-section-head home-section-head-spaced", id: "home-dashboard" },
    el("div", {},
      el("div", { class: "section-kicker" }, "A QUICK READ"),
      el("h2", { class: "section-title" }, "投递概览"),
      el("p", { class: "section-sub muted" }, "看见节奏，比盯着数字更有用")
    )
  ));
  shell.appendChild(el("div", { id: "dash-funnel" }, el("div", { class: "loading" }, "加载图表…")));
  page.appendChild(shell);
}

function homeDateLabel() {
  var now = new Date();
  var weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return (now.getMonth() + 1) + "月" + now.getDate() + "日 · " + weekdays[now.getDay()];
}

function homeStat(icon, num, label, tone, onclick) {
  return el("button", { class: "home-stat home-stat-" + tone, onclick: onclick },
    el("span", { class: "home-stat-icon" }, icon),
    el("span", { class: "home-stat-copy" },
      el("strong", {}, String(num)),
      el("small", {}, label)
    ),
    el("span", { class: "home-stat-arrow", "aria-hidden": "true" }, "↗")
  );
}

function renderDeadlinePushes(items) {
  var visible = items.slice(0, 6);
  var card = el("section", { class: "home-focus-card push-card" });
  card.appendChild(el("div", { class: "focus-card-header" },
    el("div", {},
      el("div", { class: "section-kicker" }, "ATTENTION NEEDED"),
      el("h2", {}, "今日推送")
    ),
    el("span", { class: "focus-count " + (visible.length ? "has-items" : "") }, visible.length ? visible.length + " 项" : "清爽")
  ));

  var list = el("div", { class: "push-list" });
  if (!visible.length) {
    list.appendChild(el("div", { class: "focus-empty" },
      el("span", { class: "focus-empty-mark" }, "✓"),
      el("div", {},
        el("strong", {}, "暂无临近截止事项"),
        el("p", {}, "接下来 14 天可以按自己的节奏准备")
      )
    ));
  } else {
    visible.forEach(function(item) {
      var target = item.action === "track" ? "track" : "jobs";
      list.appendChild(el("button", { class: "push-item push-" + (item.tone || "normal"), onclick: function() {
        if (target === "track" && item.application_id) window._trackFocusId = item.application_id;
        showPage(target);
      } },
        el("span", { class: "push-icon" }, item.kind === "exam_deadline" ? "笔" : "岗"),
        el("span", { class: "push-copy" },
          el("strong", {}, item.title || "未命名事项"),
          el("span", {}, item.company + " · " + item.meta)
        ),
        el("span", { class: "push-countdown" },
          el("strong", {}, formatNotificationDays(item)),
          el("small", {}, item.label)
        )
      ));
    });
  }
  card.appendChild(list);
  if (items.length > visible.length) {
    card.appendChild(el("div", { class: "focus-card-foot" }, "还有 " + (items.length - visible.length) + " 项提醒 · 已按紧急程度排序"));
  } else {
    card.appendChild(el("div", { class: "focus-card-foot" }, "优先处理红色提醒，给自己留出缓冲时间"));
  }
  return card;
}

function renderTodaySchedules(schedules) {
  var card = el("section", { class: "home-focus-card schedule-card" });
  card.appendChild(el("div", { class: "focus-card-header" },
    el("div", {},
      el("div", { class: "section-kicker" }, "YOUR DAY"),
      el("h2", {}, "今日安排")
    ),
    el("button", { class: "text-action", onclick: function() { showPage("calendar"); } }, "打开日历 →")
  ));

  var list = el("div", { class: "today-list today-list-modern" });
  if (!schedules.length) {
    list.appendChild(el("div", { class: "focus-empty schedule-empty" },
      el("span", { class: "focus-empty-mark calm" }, "—"),
      el("div", {},
        el("strong", {}, "今天没有固定日程"),
        el("p", {}, "可以安排一段专注时间，推进一个岗位")
      )
    ));
  } else {
    schedules.forEach(function(s) {
      var time = (s.scheduled_at || "").slice(11, 16) || "—";
      var eventDate = s.scheduled_at ? new Date(s.scheduled_at) : null;
      var now = Date.now();
      var isSoon = eventDate && eventDate.getTime() >= now && eventDate.getTime() - now < 90 * 60 * 1000;
      list.appendChild(el("button", { class: "today-item today-item-modern" + (isSoon ? " is-soon" : ""), onclick: function() { showPage("track"); } },
        el("span", { class: "today-time-modern" }, time),
        el("span", { class: "today-rail" }, el("span", { class: "today-dot" })),
        el("span", { class: "today-content" },
          el("strong", {}, s.company + " · " + s.stage),
          el("span", { class: "today-meta" },
            s.form ? el("span", { class: "chip sm" }, s.form) : null,
            s.location ? el("span", {}, s.location) : null,
            isSoon ? el("span", { class: "today-now" }, "即将开始") : null
          )
        )
      ));
    });
  }
  card.appendChild(list);
  card.appendChild(el("div", { class: "focus-card-foot" }, schedules.length ? "按时间排列 · 点击可回到流程跟踪" : "安排不宜太满，给自己留一点余地"));
  return card;
}

function todoCategoryClass(category) {
  return {
    "评测": "assessment",
    "面试准备": "interview",
    "面试": "interview",
    "投递": "apply",
    "材料": "material",
    "其他": "other"
  }[category] || "other";
}

function todoDueLabel(todo) {
  if (todo.is_done) return "已完成";
  if (!todo.due_at) return "无截止时间";
  var left = daysLeft(todo.due_at);
  var time = todo.due_at.slice(11, 16);
  if (left < 0) return "已逾期" + (time ? " · " + time : "");
  if (left === 0) return "今天" + (time ? " · " + time : "");
  if (left === 1) return "明天" + (time ? " · " + time : "");
  return todo.due_at.slice(5, 10).replace("-", "月") + "日" + (time ? " · " + time : "");
}

function todoDueClass(todo) {
  if (todo.is_done || !todo.due_at) return "";
  var left = daysLeft(todo.due_at);
  if (left < 0) return "is-overdue";
  if (left <= 1) return "is-urgent";
  return "";
}

function renderTodoCard(initialTodos) {
  var todos = (initialTodos || []).map(function(item) {
    return Object.assign({}, item);
  });
  var card = el("section", { class: "home-focus-card todo-card" });
  var count = el("span", { class: "focus-count todo-count" });
  var list = el("div", { class: "todo-list" });
  var foot = el("div", { class: "focus-card-foot todo-foot" });

  card.appendChild(el("div", { class: "focus-card-header" },
    el("div", {},
      el("div", { class: "section-kicker" }, "SMALL WINS"),
      el("h2", {}, "待办清单")
    ),
    el("div", { class: "todo-header-actions" },
      count,
      el("button", { class: "text-action todo-add", type: "button", onclick: function() {
        showTodoEditor(null, function(created) {
          todos.unshift(created);
          paint();
        });
      } }, "+ 新建")
    )
  ));
  card.appendChild(list);
  card.appendChild(foot);

  function sortedTodos() {
    return todos.slice().sort(function(a, b) {
      if (!!a.is_done !== !!b.is_done) return a.is_done ? 1 : -1;
      if (!a.due_at && b.due_at) return 1;
      if (a.due_at && !b.due_at) return -1;
      if (a.due_at && b.due_at && a.due_at !== b.due_at) {
        return a.due_at < b.due_at ? -1 : 1;
      }
      return (b.id || 0) - (a.id || 0);
    });
  }

  function paint() {
    var pending = todos.filter(function(todo) { return !todo.is_done; });
    var ordered = sortedTodos();
    var visible = ordered.slice(0, 8);
    count.textContent = pending.length ? pending.length + " 待完成" : (ordered.length ? "全部完成" : "从这里开始");
    count.classList.toggle("has-items", pending.length > 0);
    list.innerHTML = "";

    if (!visible.length) {
      list.appendChild(el("div", { class: "todo-empty" },
        el("span", { class: "todo-empty-mark" }, "✦"),
        el("div", {},
          el("strong", {}, "把下一步写下来"),
          el("p", {}, "例如：完成在线测评、准备一面自我介绍")
        )
      ));
    } else {
      visible.forEach(function(todo) {
        var row = el("div", { class: "todo-item" + (todo.is_done ? " is-done" : "") });
        var check = el("button", {
          class: "todo-check" + (todo.is_done ? " is-done" : ""),
          type: "button",
          title: todo.is_done ? "标记为未完成" : "标记为已完成",
          "aria-label": todo.is_done ? "标记为未完成" : "标记为已完成",
          "aria-pressed": String(!!todo.is_done),
          disabled: !!todo._saving,
          onclick: function(event) {
            event.stopPropagation();
            toggleTodo(todo);
          }
        }, todo.is_done ? "✓" : "");
        var content = el("button", {
          class: "todo-content",
          type: "button",
          title: todo.notes || "点击编辑",
          onclick: function() {
            showTodoEditor(todo, function(updated) {
              var index = todos.indexOf(todo);
              if (index >= 0) todos[index] = updated;
              paint();
            });
          }
        },
          el("strong", { class: "todo-title" }, todo.title),
          el("span", { class: "todo-meta" },
            el("span", { class: "todo-category todo-category-" + todoCategoryClass(todo.category) }, todo.category || "其他"),
            el("span", { class: "todo-due " + todoDueClass(todo) }, todoDueLabel(todo))
          )
        );
        var remove = el("button", {
          class: "todo-delete",
          type: "button",
          title: "删除待办",
          "aria-label": "删除待办",
          disabled: !!todo._saving,
          onclick: function(event) {
            event.stopPropagation();
            deleteTodo(todo);
          }
        }, "×");
        row.appendChild(check);
        row.appendChild(content);
        row.appendChild(remove);
        list.appendChild(row);
      });
    }

    if (todos.length > visible.length) {
      foot.textContent = "还有 " + (todos.length - visible.length) + " 项 · 点击任务文字可编辑";
    } else {
      foot.textContent = todos.length ? "点击圆圈完成 · 点击任务文字编辑" : "评测、面试准备和材料提交，都可以放在这里";
    }
  }

  function toggleTodo(todo) {
    if (todo._saving) return;
    var previous = todo.is_done;
    todo._saving = true;
    todo.is_done = !previous;
    paint();
    API.patch("/api/todos/" + todo.id, { is_done: todo.is_done }).then(function(updated) {
      var index = todos.indexOf(todo);
      if (index >= 0) todos[index] = updated;
      paint();
      toast(updated.is_done ? "已完成，划掉啦" : "已恢复待办");
    }).catch(function() {
      todo.is_done = previous;
      todo._saving = false;
      paint();
      toast("更新待办失败");
    });
  }

  function deleteTodo(todo) {
    if (!confirm("确认删除这个待办吗？")) return;
    todo._saving = true;
    paint();
    API.del("/api/todos/" + todo.id).then(function() {
      todos = todos.filter(function(item) { return item !== todo; });
      paint();
      toast("待办已删除");
    }).catch(function() {
      todo._saving = false;
      paint();
      toast("删除待办失败");
    });
  }

  paint();
  return card;
}

function showTodoEditor(todo, onSaved) {
  var editing = !!todo;
  var categories = ["评测", "面试准备", "投递", "材料", "其他"];
  var category = todo && todo.category ? todo.category : "评测";
  var body = el("div", { class: "todo-editor" },
    formRow("任务 *", el("input", {
      class: "input", id: "todo-title", maxlength: "200",
      placeholder: "例如：完成 XX 公司在线测评",
      value: todo ? todo.title : ""
    })),
    formRow("分类", el("select", { class: "select", id: "todo-category" },
      ...categories.map(function(item) {
        return el("option", { value: item, selected: item === category ? true : undefined }, item);
      })
    )),
    formRow("截止时间（可选）", el("input", {
      class: "input", id: "todo-due", type: "datetime-local",
      value: todo && todo.due_at ? todo.due_at.slice(0, 16) : ""
    })),
    formRow("备注（可选）", el("textarea", {
      class: "textarea", id: "todo-notes", placeholder: "会议链接、准备重点或提醒"
    }, todo && todo.notes ? todo.notes : ""))
  );

  showModal(editing ? "编辑待办" : "新建待办", body, [
    el("button", { class: "btn primary", type: "button", onclick: async function() {
      var title = val("todo-title");
      if (!title) { toast("请先写下任务内容"); return; }
      var payload = {
        title: title,
        category: val("todo-category") || "其他",
        due_at: val("todo-due") || null,
        notes: val("todo-notes") || null
      };
      try {
        var saved = editing
          ? await API.patch("/api/todos/" + todo.id, payload)
          : await API.post("/api/todos", payload);
        closeModal();
        if (onSaved) onSaved(saved);
        toast(editing ? "待办已更新" : "待办已添加");
      } catch (e) {
        toast("保存失败: " + e.message);
      }
    } }, editing ? "保存" : "添加"),
    el("button", { class: "btn", type: "button", onclick: closeModal }, "取消")
  ]);
}

function renderGroupActivity(activity) {
  var contributors = activity.contributors || [];
  return el("button", { class: "activity-card activity-card-modern", onclick: function() { showPage("jobs"); } },
    el("span", { class: "activity-orb" }, activity.total || 0),
    el("span", { class: "activity-main" },
      el("span", { class: "activity-kicker" }, "GROUP PULSE"),
      el("strong", { class: "activity-title" }, activity.total ? "今天群里新增了 " + activity.total + " 个岗位" : "今天群里还没有新增岗位"),
      el("span", { class: "activity-contributors" },
        ...contributors.slice(0, 4).map(function(item) {
          return el("span", { class: "activity-person" },
            renderUserAvatar(item, "tiny"),
            (item.nickname || "群友") + " +" + item.count
          );
        }),
        !activity.total ? el("span", { class: "muted" }, "去岗位库看看新的机会") : null
      )
    ),
    el("span", { class: "activity-arrow" }, "→")
  );
}

function renderActiveAppSection(apps) {
  var empty = !apps || !apps.length;
  var card = el("section", { class: "card section-card app-section-card app-section-accent home-active-section", id: "home-active-section" },
    el("div", { class: "card-header" },
      el("div", {},
        el("div", { class: "section-kicker" }, "IN MOTION"),
        el("h3", { class: "card-title" }, "进行中"),
        el("div", { class: "text-sm muted" }, "当前流程中的投递")
      ),
      !empty ? el("span", { class: "badge" }, apps.length) : null
    )
  );
  card.appendChild(empty
    ? el("div", { class: "empty-mini" }, "暂无数据")
    : el("div", { class: "app-scroll" },
        ...apps.map(function(a) {
          return el("button", { class: "mini-app-card mini-app-card-modern", onclick: function() { showPage("track"); } },
            el("span", { class: "mini-app-marker" }),
            el("span", { class: "mini-app-copy" },
              el("strong", { class: "mini-job-company" }, a.company),
              el("span", { class: "mini-job-title" }, a.title),
              el("span", { class: "mini-job-meta" },
                el("span", { class: "chip sm" }, a.current_stage),
                el("span", { class: "muted text-sm" }, a.status)
              )
            ),
            el("span", { class: "mini-app-arrow" }, "↗")
          );
        })
      )
  );
  return card;
}
