var calYear, calMonth;
var typeLabels = { "job_deadline": "岗位截止", "application_stage": "面试安排", "todo_deadline": "待投递" };
var typeColors = { "job_deadline": "#ff3b30", "application_stage": "#007aff", "todo_deadline": "#ff9500" };
var typeBgColors = { "job_deadline": "rgba(255,59,48,0.08)", "application_stage": "rgba(0,122,255,0.08)", "todo_deadline": "rgba(255,149,0,0.08)" };
var _calVisibleTypes = { "job_deadline": true, "application_stage": true, "todo_deadline": true };

window.load_calendar = async function() {
  var now = new Date();
  calYear = now.getFullYear();
  calMonth = now.getMonth() + 1;
  renderCalendarPage();
};

async function renderCalendarPage() {
  var page = document.getElementById("page-calendar");
  page.innerHTML = "";
  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "日历视图"),
      el("div", { class: "page-sub muted" }, "一览所有面试安排和截止日期")
    ),
    el("div", { class: "cal-nav" },
      el("button", { class: "btn sm", onclick: function() { prevMonth(); } }, "‹"),
      el("span", { class: "cal-month-label", id: "cal-label" }, calYear + "年" + calMonth + "月"),
      el("button", { class: "btn sm", onclick: function() { nextMonth(); } }, "›"),
      el("button", { class: "btn sm", onclick: function() { goToday(); } }, "今天")
    )
  ));

  // 统计概览
  page.appendChild(el("div", { class: "cal-stats", id: "cal-stats" }));
  // 类型筛选
  page.appendChild(el("div", { class: "cal-type-filters", id: "cal-type-filters" }));
  // 日历
  page.appendChild(el("div", { class: "card" },
    el("div", { id: "cal-grid" }, el("div", { class: "loading" }, "加载中…"))
  ));
  // 事件列表
  page.appendChild(el("div", { class: "card mt-16" },
    el("div", { class: "card-header" },
      el("h3", { class: "card-title" }, "📋 本月事件")
    ),
    el("div", { id: "cal-events" }, el("div", { class: "loading" }, "加载中…"))
  ));
  await loadCalendarData();
}

async function loadCalendarData() {
  try {
    var data = await API.get("/api/calendar/month?year=" + calYear + "&month=" + calMonth);
    renderCalGrid(data.events || []);
    renderEventList(data.events || []);
    // 加载统计
    try {
      var stats = await API.get("/api/calendar/month/stats?year=" + calYear + "&month=" + calMonth);
      renderCalStats(stats);
    } catch(e) {}
  } catch(e) {
    document.getElementById("cal-grid").innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

function renderCalStats(stats) {
  var box = document.getElementById("cal-stats");
  if (!box) return;
  box.innerHTML = "";

  // 总统计
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

  // 按类型统计 + 筛选
  var filterBox = document.getElementById("cal-type-filters");
  if (filterBox) {
    filterBox.innerHTML = "";
    filterBox.appendChild(el("div", { class: "cal-type-stats" },
      ...Object.keys(typeLabels).map(function(type) {
        var count = 0;
        // 从 stats.by_stage 估算，或从当前事件计算
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
  // 重新渲染
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
          var title = e.title.length > 6 ? e.title.slice(0, 6) + '…' : e.title;
          eventsHtml += '<div class="cal-event" style="border-left-color:' + color + ';background:' + bg + '" title="' + e.title + '">' + title + '</div>';
        });
        if (dayEvents.length > 3) eventsHtml += '<div class="cal-more">+' + (dayEvents.length - 3) + '</div>';
        html += '<div class="cal-cell' + (isToday ? ' cal-today' : '') + '"><div class="cal-day-num">' + dayCount + '</div>' + eventsHtml + '</div>';
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

function renderEventList(events) {
  var box = document.getElementById("cal-events");
  var visibleEvents = events.filter(function(e) { return _calVisibleTypes[e.type] !== false; });
  if (!visibleEvents.length) { box.innerHTML = ""; box.appendChild(emptyState("本月暂无事件")); return; }
  // 按日期+时间排序
  visibleEvents.sort(function(a, b) {
    var cmp = a.date.localeCompare(b.date);
    if (cmp !== 0) return cmp;
    // 同一天内按时间排序
    var ta = a.time || "";
    var tb = b.time || "";
    return ta.localeCompare(tb);
  });
  box.innerHTML = "";
  // 按日期分组
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
        el("span", { class: "chip sm", style: "color:" + color }, typeLabels[e.type] || e.type),
        e.time ? el("span", { class: "text-sm" }, "🕐 " + e.time) : null,
        e.location ? el("span", { class: "text-sm" }, "📍 " + e.location) : null,
        e.form ? el("span", { class: "text-sm" }, "📋 " + e.form) : null,
        e.url ? el("a", { href: e.url, target: "_blank", class: "text-sm link", onclick: function(ev) { ev.stopPropagation(); } }, "🔗 链接") : null
      )
    );
    box.appendChild(el("div", { class: "event-item" },
      el("div", { class: "event-time-col" }, e.time ? e.time : ""),
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
  document.getElementById("cal-label").textContent = calYear + "年" + calMonth + "月";
  loadCalendarData();
}
function nextMonth() {
  calMonth++;
  if (calMonth > 12) { calMonth = 1; calYear++; }
  document.getElementById("cal-label").textContent = calYear + "年" + calMonth + "月";
  loadCalendarData();
}
function goToday() {
  var now = new Date();
  calYear = now.getFullYear();
  calMonth = now.getMonth() + 1;
  document.getElementById("cal-label").textContent = calYear + "年" + calMonth + "月";
  loadCalendarData();
}
