window.load_home = async function() {
  var page = document.getElementById("page-home");
  page.innerHTML = '<div class="loading">加载中…</div>';
  try {
    var data = await API.get("/api/home");
    page.innerHTML = "";

    var hour = new Date().getHours();
    var greeting = hour < 12 ? "早上好" : hour < 18 ? "下午好" : "晚上好";
    page.appendChild(el("div", { class: "welcome-banner" },
      el("div", { class: "welcome-text" },
        el("div", { class: "eyebrow" }, (data.group && data.group.name) || "MY JOB JOURNEY"),
        el("h2", {}, greeting + "，" + ((currentUser && currentUser.nickname) || "求职人")),
        el("p", {}, (currentUser && currentUser.bio) || "把投递、面试和 Offer 都放在一处跟进")
      )
    ));

    var s = data.stats;
    var newCount = s.new_today_count || 0;
    page.appendChild(renderGroupActivity(data.job_activity_today || { total: newCount, contributors: [] }));

    page.appendChild(el("div", { class: "stats-grid" },
      statCard("↻", s.in_progress_count || 0, "进行中", "info", "track"),
      statCard("✕", s.rejected_count || 0, "已淘汰", "gray", "track"),
      statCard("★", s.offer_count, "Offer", "green", "offers"),
      statCard("☰", s.total_apps, "总投递", "purple", "track")
    ));

    if (data.today_schedules && data.today_schedules.length) {
      page.appendChild(renderTodaySchedules(data.today_schedules));
    }

    var twoCol = el("div", { class: "two-col" });
    twoCol.appendChild(renderAppSection("进行中", "当前流程中的投递", data.in_progress_apps, "info"));
    twoCol.appendChild(renderAppSection("已淘汰", "流程已结束的投递", data.rejected_apps, "gray"));
    page.appendChild(twoCol);
  } catch(e) {
    page.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
};

function renderGroupActivity(activity) {
  var contributors = activity.contributors || [];
  return el("div", { class: "activity-card", onclick: function() { showPage("jobs"); } },
    el("div", { class: "activity-orb" }, activity.total || 0),
    el("div", { class: "activity-main" },
      el("div", { class: "activity-kicker" }, "TODAY IN YOUR GROUP"),
      el("div", { class: "activity-title" },
        activity.total ? "今天群里新增了 " + activity.total + " 个岗位" : "今天还没有人添加岗位"
      ),
      el("div", { class: "activity-contributors" },
        ...contributors.slice(0, 4).map(function(item) {
          return el("span", { class: "activity-person" },
            renderUserAvatar(item, "tiny"),
            (item.nickname || "群友") + " +" + item.count
          );
        }),
        activity.sync_count ? el("span", { class: "activity-person sync" }, "表格同步 +" + activity.sync_count) : null,
        !activity.total ? el("span", { class: "muted" }, "成为今天第一个分享岗位的人") : null
      )
    ),
    el("span", { class: "activity-arrow" }, "→")
  );
}

function statCard(icon, num, label, color, targetPage) {
  return el("div", { class: "stat-card stat-" + color + (targetPage ? " clickable" : ""), onclick: targetPage ? function() { showPage(targetPage); } : null },
    el("div", { class: "stat-icon" }, icon),
    el("div", { class: "stat-body" },
      el("div", { class: "stat-num" }, num),
      el("div", { class: "stat-label" }, label)
    )
  );
}

function renderTodaySchedules(schedules) {
  return el("div", { class: "card today-card" },
    el("div", { class: "card-header" },
      el("h3", { class: "card-title" }, "今日日程"),
      el("span", { class: "badge" }, schedules.length + " 项")
    ),
    el("div", { class: "today-list" },
      ...schedules.map(function(s) {
        return el("div", { class: "today-item" },
          el("div", { class: "today-time-col" },
            el("div", { class: "today-time" }, (s.scheduled_at || "").slice(11, 16)),
            el("div", { class: "today-dot" })
          ),
          el("div", { class: "today-content" },
            el("div", { class: "today-title" }, s.company + " · " + s.stage),
            el("div", { class: "today-meta" },
              s.form ? el("span", { class: "chip sm" }, s.form) : null,
              s.location ? el("span", { class: "muted text-sm" }, s.location) : null
            )
          )
        );
      })
    )
  );
}

function renderAppSection(title, subtitle, apps, tone) {
  var empty = !apps || !apps.length;
  return el("div", { class: "card section-card" },
    el("div", { class: "card-header" },
      el("div", {},
        el("h3", { class: "card-title" }, title),
        el("div", { class: "text-sm muted" }, subtitle)
      ),
      !empty ? el("span", { class: "badge" }, apps.length) : null
    ),
    empty
      ? el("div", { class: "empty-mini" }, "暂无数据")
      : el("div", { class: "app-scroll" },
          ...apps.map(function(a) {
            return el("div", { class: "mini-app-card", onclick: function() { showPage("track"); } },
              el("div", { class: "mini-job-company" }, a.company),
              el("div", { class: "mini-job-title" }, a.title),
              el("div", { class: "mini-job-meta" },
                el("span", { class: "chip sm" }, a.current_stage),
                el("span", { class: "muted text-sm" }, a.status)
              )
            );
          })
        )
  );
}
