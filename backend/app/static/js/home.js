window.load_home = async function() {
  var page = document.getElementById("page-home");
  page.innerHTML = '<div class="loading">加载中…</div>';
  try {
    var data = await API.get("/api/home");
    page.innerHTML = "";

    // 欢迎横幅
    var nickname = currentUser ? (currentUser.nickname || currentUser.username) : "";
    var hour = new Date().getHours();
    var greeting = hour < 12 ? "早上好" : hour < 18 ? "下午好" : "晚上好";
    var motivations = [
      "秋招路上，每一步都算数！",
      "今天也要元气满满地投简历呀~",
      "机会是留给有准备的人的，冲！",
      "每一次面试都是成长，加油！",
      "坚持就是胜利，offer在向你招手！",
      "你已经很棒了，继续保持！",
      "今天投递的简历，就是明天的offer~",
      "相信自己，好运正在路上！",
      "秋招虽累，但未来可期！",
      "稳住心态，一个一个拿下！",
      "每天进步一点点，秋招必上岸！",
      "不要焦虑，你的offer会来的！"
    ];
    var randomMotivation = motivations[Math.floor(Math.random() * motivations.length)];
    page.appendChild(el("div", { class: "welcome-banner" },
      el("div", { class: "welcome-text" },
        el("h2", {}, greeting + "，" + nickname),
        el("p", { class: "muted" }, randomMotivation)
      )
    ));

    // 统计卡片 - 两行网格，点击跳转
    var s = data.stats;
    page.appendChild(el("div", { class: "stats-grid" },
      statCard("💼", s.total_jobs, "岗位总数", "blue", "jobs"),
      statCard("📋", s.total_apps, "投递记录", "purple", "track"),
      statCard("🔄", s.in_progress_count || 0, "进行中", "orange", "track"),
      statCard("⏰", s.closing_count, "即将截止", "red", "jobs"),
      statCard("📅", s.schedule_count, "今日日程", "teal", "calendar"),
      statCard("🎉", s.offer_count, "Offer", "green", "offers"),
      statCard("❌", s.rejected_count || 0, "已淘汰", "gray", "track")
    ));

    // 今日待办
    if (data.today_schedules && data.today_schedules.length) {
      page.appendChild(renderTodaySchedules(data.today_schedules));
    }

    // 两列布局：新开岗位 + 即将截止
    var twoCol = el("div", { class: "two-col" });
    twoCol.appendChild(renderJobSection("🆕 新开岗位", "最近一周新增", data.new_jobs));
    twoCol.appendChild(renderJobSection("⏰ 即将截止", "7天内截止", data.closing_jobs, true));
    page.appendChild(twoCol);

    // 匹配推荐
    if (data.matched && data.matched.length) {
      page.appendChild(renderJobSection("🎯 匹配推荐", "根据偏好智能推荐", data.matched, false, true));
    }
  } catch(e) {
    page.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
};

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
      el("h3", { class: "card-title" }, "📌 今日待办"),
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
              s.location ? el("span", { class: "muted text-sm" }, "📍 " + s.location) : null
            )
          )
        );
      })
    )
  );
}

function renderJobSection(title, subtitle, items, isClosing, showScore) {
  var empty = !items || !items.length;
  return el("div", { class: "card section-card" },
    el("div", { class: "card-header" },
      el("div", {},
        el("h3", { class: "card-title" }, title),
        el("div", { class: "text-sm muted" }, subtitle)
      ),
      !empty ? el("span", { class: "badge" }, items.length) : null
    ),
    empty
      ? el("div", { class: "empty-mini" }, "暂无数据")
      : el("div", { class: "job-scroll" },
          ...items.slice(0, 8).map(function(j) { return miniJobCard(j, isClosing, showScore); })
        )
  );
}

function miniJobCard(j, isClosing, showScore) {
  var dl = j.close_date ? Math.ceil((new Date(j.close_date) - new Date()) / 86400000) : null;
  return el("div", { class: "mini-job-card", onclick: function() { showJobDetailFromHome(j); } },
    el("div", { class: "mini-job-left" },
      el("div", { class: "mini-job-company" }, j.company),
      el("div", { class: "mini-job-title" }, j.title),
      el("div", { class: "mini-job-meta" },
        j.location ? el("span", {}, "📍 " + j.location) : null,
        j.salary ? el("span", {}, "💰 " + j.salary) : null
      )
    ),
    el("div", { class: "mini-job-right" },
      showScore && j.match_score
        ? el("div", { class: "match-ring " + (j.match_score >= 70 ? "high" : j.match_score >= 40 ? "mid" : "low") }, j.match_score)
        : isClosing && dl !== null
          ? el("div", { class: "deadline-chip " + (dl <= 3 ? "urgent" : "warn") }, dl + "天")
          : j.close_date
            ? el("div", { class: "text-sm muted" }, "截止 " + j.close_date.slice(5))
            : null
    )
  );
}

async function showJobDetailFromHome(j) {
  try {
    var data = await API.get("/api/jobs/" + j.id);
    if (data && typeof showJobDetail === "function") showJobDetail(data);
  } catch(e) { toast("加载失败"); }
}
