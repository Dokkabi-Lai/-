var calYear, calMonth;
var typeLabels = { exam: "笔试", deadline: "笔试截止", interview: "面试", other: "其他安排" };
var typeColors = { exam: "#0f766e", deadline: "#d97706", interview: "#2563eb", other: "#b45309" };
var typeBgColors = {
  exam: "rgba(15,118,110,0.12)",
  deadline: "rgba(217,119,6,0.14)",
  interview: "rgba(37,99,235,0.12)",
  other: "rgba(180,83,9,0.12)"
};
var _calVisibleTypes = { exam: true, deadline: true, interview: true, other: true };

window.load_calendar = async function() {
  var now = new Date();
  calYear = now.getFullYear();
  calMonth = now.getMonth() + 1;
  renderCalendarPage();
};

async function renderCalendarPage() {
  var page = document.getElementById("page-calendar");
  page.innerHTML = "";
  var shell = el("div", { class: "calendar-shell" });
  shell.appendChild(el("section", { class: "calendar-hero" },
    el("div", { class: "calendar-hero-copy" },
      el("div", { class: "section-kicker" }, "TIMEBOX"),
      el("h1", { class: "calendar-title" }, "日历"),
      el("p", {}, "把固定时间和截止时间放进同一条清晰的节奏里。")
    )
  ));

  shell.appendChild(el("section", { class: "calendar-control-card" },
    el("div", { class: "calendar-control-top" },
      el("div", {},
        el("div", { class: "section-kicker" }, "MONTH SIGNAL"),
        el("h2", {}, "这个月的节奏"),
        el("p", { class: "muted" }, "先看数量，再看哪一天值得留出完整时间。")
      ),
      el("div", { class: "cal-stats", id: "cal-stats" })
    ),
    el("div", { class: "calendar-filter-row" },
      el("span", { class: "calendar-filter-label" }, "显示安排"),
      el("div", { class: "cal-type-filters", id: "cal-type-filters" })
    )
  ));

  var content = el("div", { class: "calendar-content-grid" });
  content.appendChild(el("section", { class: "card cal-month-card" },
    el("div", { class: "cal-card-head" },
      el("div", {},
        el("div", { class: "section-kicker" }, "MONTH VIEW"),
        el("h2", {}, "月视图")
      ),
      el("div", { class: "cal-month-head-actions" },
        el("div", { class: "cal-nav cal-month-nav", "aria-label": "月份切换" },
          el("button", { class: "btn sm calendar-nav-btn", "aria-label": "上个月", onclick: function() { prevMonth(); } }, "‹"),
          el("span", { class: "cal-month-label", id: "cal-label" }, calYear + "年" + calMonth + "月"),
          el("button", { class: "btn sm calendar-nav-btn", "aria-label": "下个月", onclick: function() { nextMonth(); } }, "›"),
          el("button", { class: "btn sm calendar-today-btn", onclick: function() { goToday(); } }, "今天")
        ),
        el("span", { class: "cal-card-hint" }, "日程会按颜色区分")
      )
    ),
    el("div", { id: "cal-grid" }, el("div", { class: "loading" }, "加载中…"))
  ));
  content.appendChild(el("section", { class: "card cal-agenda-card" },
    el("div", { class: "cal-card-head" },
      el("div", {},
        el("div", { class: "section-kicker" }, "AGENDA"),
        el("h2", {}, "本月安排")
      ),
      el("span", { class: "cal-card-hint" }, "按日期排列")
    ),
    el("div", { id: "cal-events" }, el("div", { class: "loading" }, "加载中…"))
  ));
  shell.appendChild(content);
  page.appendChild(shell);
  await loadCalendarData();
}

async function loadCalendarData() {
  try {
    var monthUrl = "/api/calendar/month?year=" + calYear + "&month=" + calMonth;
    var statsUrl = "/api/calendar/month/stats?year=" + calYear + "&month=" + calMonth;
    // 两个接口互不依赖，提前并行请求，减少日历首次打开的等待时间。
    var monthRequest = API.get(monthUrl);
    var statsRequest = API.get(statsUrl);
    var data = await monthRequest;
    renderCalGrid(data.events || []);
    renderEventList(data.events || []);
    statsRequest.then(function(stats) {
      renderCalStats(stats);
    }).catch(function() {});
  } catch(e) {
    document.getElementById("cal-grid").innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

function renderCalStats(stats) {
  var box = document.getElementById("cal-stats");
  if (!box) return;
  box.innerHTML = "";
  box.appendChild(el("div", { class: "cal-stats-grid" },
    el("div", { class: "cal-stat-card" },
      el("div", { class: "cal-stat-num" }, stats.total),
      el("div", { class: "cal-stat-label" }, "本月安排")
    ),
    el("div", { class: "cal-stat-card" },
      el("div", { class: "cal-stat-num upcoming" }, stats.upcoming),
      el("div", { class: "cal-stat-label" }, "待进行")
    ),
    el("div", { class: "cal-stat-card" },
      el("div", { class: "cal-stat-num completed" }, stats.completed),
      el("div", { class: "cal-stat-label" }, "已完成")
    )
  ));

  var filterBox = document.getElementById("cal-type-filters");
  if (filterBox) {
    filterBox.innerHTML = "";
    filterBox.appendChild(el("div", { class: "cal-type-stats" },
      ...Object.keys(typeLabels).map(function(type) {
        return el("label", { class: "chip-toggle " + (_calVisibleTypes[type] ? "active" : ""), onclick: function() { toggleCalType(type); } },
          el("span", { class: "cal-type-dot", style: "background:" + typeColors[type] }),
          el("span", {}, typeLabels[type])
        );
      })
    ));
  }
}

function toggleCalType(type) {
  _calVisibleTypes[type] = !_calVisibleTypes[type];
  loadCalendarData();
}

function renderCalGrid(events) {
  var grid = document.getElementById("cal-grid");
  var today = new Date();
  var todayStr = today.toISOString().slice(0, 10);
  var visibleEvents = events.filter(function(e) { return _calVisibleTypes[e.type] !== false; });
  var eventMap = {};
  visibleEvents.forEach(function(e) {
    if (!eventMap[e.date]) eventMap[e.date] = [];
    eventMap[e.date].push(e);
  });

  var firstDay = new Date(calYear, calMonth - 1, 1);
  var daysInMonth = new Date(calYear, calMonth, 0).getDate();
  var startWeekday = firstDay.getDay();
  var weekdays = ["日", "一", "二", "三", "四", "五", "六"];

  var html = '<div class="cal-table"><div class="cal-row cal-header">';
  weekdays.forEach(function(w) { html += '<div class="cal-cell">' + w + '</div>'; });
  html += '</div>';

  var dayCount = 1;
  for (var row = 0; row < 6; row++) {
    if (dayCount > daysInMonth && row > 0) break;
    html += '<div class="cal-row">';
    for (var col = 0; col < 7; col++) {
      if ((row === 0 && col < startWeekday) || dayCount > daysInMonth) {
        html += '<div class="cal-cell cal-empty"></div>';
      } else {
        var dateStr = calYear + '-' + String(calMonth).padStart(2, '0') + '-' + String(dayCount).padStart(2, '0');
        var dayEvents = eventMap[dateStr] || [];
        var isToday = dateStr === todayStr;
        var eventsHtml = "";
        dayEvents.slice(0, 3).forEach(function(e) {
          var color = typeColors[e.type] || "#646a73";
          var bg = typeBgColors[e.type] || "var(--bg)";
          var rawTitle = e.title || e.stage || "安排";
          var title = rawTitle.length > 8 ? rawTitle.slice(0, 8) + '…' : rawTitle;
          eventsHtml += '<div class="cal-event" style="--event-color:' + color + ';border-left-color:' + color + ';background:' + bg + '" title="' + calEscape(rawTitle) + '">' + calEscape(title) + '</div>';
        });
        if (dayEvents.length > 3) eventsHtml += '<div class="cal-more">+' + (dayEvents.length - 3) + '</div>';
        html += '<div class="cal-cell' + (isToday ? ' cal-today' : '') + (dayEvents.length ? ' cal-has-events' : '') + '"><div class="cal-day-num">' + dayCount + '</div>' + eventsHtml + '</div>';
        dayCount++;
      }
    }
    html += '</div>';
  }
  html += '</div>';
  html += '<div class="cal-legend">';
  Object.keys(typeLabels).forEach(function(type) {
    html += '<span class="cal-legend-item"><span class="cal-legend-dot" style="background:' + typeColors[type] + '"></span>' + typeLabels[type] + '</span>';
  });
  html += '</div>';
  grid.innerHTML = html;
}

function calEscape(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function(ch) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
  });
}

function renderEventList(events) {
  var box = document.getElementById("cal-events");
  var visibleEvents = events.filter(function(e) { return _calVisibleTypes[e.type] !== false; });
  if (!visibleEvents.length) { box.innerHTML = ""; box.appendChild(emptyState("本月暂无笔试或面试安排")); return; }
  visibleEvents.sort(function(a, b) {
    var cmp = a.date.localeCompare(b.date);
    if (cmp !== 0) return cmp;
    return (a.time || "").localeCompare(b.time || "");
  });
  box.innerHTML = "";
  var currentDate = "";
  visibleEvents.forEach(function(e) {
    var color = typeColors[e.type] || "#646a73";
    if (e.date !== currentDate) {
      currentDate = e.date;
      box.appendChild(el("div", { class: "event-date-header" }, e.date.slice(5) + " " + _weekdayName(e.date)));
    }
    var infoContent = el("div", { class: "event-info" },
      el("div", { class: "event-title" }, e.title),
      el("div", { class: "event-meta" },
        el("span", { class: "chip sm", style: "color:" + color }, typeLabels[e.type] || e.stage || e.type),
        e.type === "deadline" ? el("span", { class: "text-sm deadline-label" }, "截止前完成") : (e.time ? el("span", { class: "text-sm" }, e.time) : null),
        e.location ? el("span", { class: "text-sm" }, e.location) : null,
        e.form ? el("span", { class: "text-sm" }, e.form) : null
      )
    );
    box.appendChild(el("div", { class: "event-item" },
      el("div", { class: "event-time-col" }, e.type === "deadline" ? "截止" : (e.time ? e.time : "")),
      el("div", { class: "event-dot", style: "background:" + color }),
      infoContent
    ));
  });
}

function _weekdayName(dateStr) {
  var d = new Date(dateStr);
  return ["周日","周一","周二","周三","周四","周五","周六"][d.getDay()];
}

function prevMonth() {
  calMonth--;
  if (calMonth < 1) { calMonth = 12; calYear--; }
  updateCalLabel();
  loadCalendarData();
}
function nextMonth() {
  calMonth++;
  if (calMonth > 12) { calMonth = 1; calYear++; }
  updateCalLabel();
  loadCalendarData();
}
function goToday() {
  var now = new Date();
  calYear = now.getFullYear();
  calMonth = now.getMonth() + 1;
  updateCalLabel();
  loadCalendarData();
}

function updateCalLabel() {
  var label = document.getElementById("cal-label");
  if (label) label.textContent = calYear + "年" + calMonth + "月";
}
