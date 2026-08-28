window.load_review = async function() {
  var page = document.getElementById("page-review");
  page.innerHTML = "";
  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "投递仪表盘"),
      el("div", { class: "page-sub muted" }, "用图表看进度、淘汰环节和每周投递量")
    )
  ));
  page.appendChild(el("div", { id: "dash-funnel" }, el("div", { class: "loading" }, "加载中…")));
  page.appendChild(el("div", { id: "review-list" }));
  loadDashboard();
  loadReviews();
};

async function loadDashboard() {
  var box = document.getElementById("dash-funnel");
  if (!box) return;
  try {
    var d = await API.get("/api/applications/dashboard");
    box.innerHTML = "";
    var funnel = d.funnel || {};
    var funnelItems = [
      { label: "已投递", value: funnel["投递"] || 0, color: "#c45c26" },
      { label: "简历筛选", value: funnel["简历筛选"] || 0, color: "#b45309" },
      { label: "笔试", value: funnel["笔试"] || 0, color: "#0f766e" },
      { label: "面试", value: funnel["面试"] || 0, color: "#2563eb" },
      { label: "Offer", value: funnel["Offer"] || 0, color: "#2f7d57" }
    ];
    box.appendChild(chartCard("投递漏斗", renderFunnel(funnelItems)));

    var charts = el("div", { class: "chart-grid" });
    var st = d.by_status || {};
    charts.appendChild(chartCard("状态分布", renderDonut([
      { label: "进行中", value: st["进行中"] || 0, color: "#2563eb" },
      { label: "已淘汰", value: st["已淘汰"] || 0, color: "#8a8174" },
      { label: "Offer", value: st["已完成"] || 0, color: "#2f7d57" }
    ])));
    var stages = d.by_stage || {};
    charts.appendChild(chartCard("当前所在阶段", renderBars(Object.keys(stages).map(function(k) {
      return { label: k, value: stages[k] || 0, color: "#c45c26" };
    }))));
    box.appendChild(charts);

    var charts2 = el("div", { class: "chart-grid" });
    var rejects = d.reject_by_stage || {};
    var rejectItems = Object.keys(rejects).map(function(k) {
      return { label: k, value: rejects[k], color: "#c2413b" };
    });
    charts2.appendChild(chartCard("淘汰发生在", rejectItems.length ? renderBars(rejectItems) : emptyChart("还没有淘汰记录")));
    charts2.appendChild(chartCard("近 8 周投递量", renderColumns(d.weekly || [])));
    box.appendChild(charts2);
  } catch(e) {
    box.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

function chartCard(title, node) {
  return el("div", { class: "card chart-card" },
    el("h3", { class: "card-title" }, title),
    node
  );
}

function emptyChart(text) {
  return el("div", { class: "empty-mini" }, text);
}

function renderFunnel(items) {
  var max = Math.max.apply(null, items.map(function(i) { return i.value; }).concat([1]));
  var wrap = el("div", { class: "funnel-visual" });
  items.forEach(function(item, idx) {
    var pct = Math.max(28, Math.round(item.value / max * 100));
    wrap.appendChild(el("div", { class: "funnel-row" },
      el("div", { class: "funnel-label-col" }, item.label),
      el("div", { class: "funnel-bar-col" },
        el("div", { class: "funnel-bar", title: item.label + "：" + item.value, style: "width:" + pct + "%;background:" + item.color },
          el("span", {}, item.value)
        )
      )
    ));
  });
  return wrap;
}

function renderDonut(items) {
  var total = items.reduce(function(s, i) { return s + i.value; }, 0);
  var size = 180, cx = 90, cy = 90, r = 58, sw = 22;
  var circ = 2 * Math.PI * r;
  var offset = 0;
  var rings = [];
  if (!total) {
    rings.push('<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="#ebe6dc" stroke-width="' + sw + '"></circle>');
  } else {
    items.forEach(function(item) {
      if (!item.value) return;
      var len = item.value / total * circ;
      rings.push(
        '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + item.color +
        '" stroke-width="' + sw + '" stroke-dasharray="' + len + ' ' + (circ - len) +
        '" stroke-dashoffset="' + (-offset) + '" stroke-linecap="butt" transform="rotate(-90 ' + cx + ' ' + cy + ')"></circle>'
      );
      offset += len;
    });
  }
  var svg = '<svg viewBox="0 0 ' + size + ' ' + size + '" class="donut-svg">' + rings.join("") +
    '<text x="' + cx + '" y="' + (cy - 2) + '" text-anchor="middle" font-size="22" font-weight="700" fill="#1f1a14">' + total + '</text>' +
    '<text x="' + cx + '" y="' + (cy + 18) + '" text-anchor="middle" font-size="11" fill="#8a8174">投递</text></svg>';
  var legend = el("div", { class: "chart-legend" },
    ...items.map(function(i) {
      return el("div", { class: "legend-item" },
        el("span", { class: "legend-dot", style: "background:" + i.color }),
        el("span", {}, i.label + " " + i.value)
      );
    })
  );
  var wrap = el("div", { class: "donut-wrap" });
  wrap.innerHTML = svg;
  wrap.appendChild(legend);
  return wrap;
}

function renderBars(items) {
  var max = Math.max.apply(null, items.map(function(i) { return i.value; }).concat([1]));
  var wrap = el("div", { class: "bar-visual" });
  items.forEach(function(item) {
    var pct = Math.round(item.value / max * 100);
    wrap.appendChild(el("div", { class: "bar-row" },
      el("div", { class: "bar-label" }, item.label),
      el("div", { class: "bar-track" },
        el("div", { class: "bar-fill", title: item.label + "：" + item.value, style: "width:" + pct + "%;background:" + (item.color || "#c45c26") })
      ),
      el("div", { class: "bar-val" }, item.value)
    ));
  });
  return wrap;
}

function renderColumns(weeks) {
  if (!weeks.length) return emptyChart("暂无数据");
  var max = Math.max.apply(null, weeks.map(function(w) { return w.count; }).concat([1]));
  var wrap = el("div", { class: "col-visual" });
  weeks.forEach(function(w) {
    var h = Math.max(4, Math.round(w.count / max * 110));
    wrap.appendChild(el("div", { class: "col-item" },
      el("div", { class: "col-val" }, w.count || ""),
      el("div", { class: "col-bar", title: w.label + "：" + w.count + " 次", style: "height:" + h + "px" }),
      el("div", { class: "col-label" }, w.label)
    ));
  });
  return wrap;
}

async function loadReviews() {
  var box = document.getElementById("review-list");
  if (!box) return;
  try {
    var data = await API.get("/api/applications/reviews/all");
    box.innerHTML = "";
    box.appendChild(el("h3", { class: "card-title mb-16" }, "面试记录"));
    if (!data.length) {
      box.appendChild(emptyState("还没有面试记录。在流程跟踪里给各阶段写反馈，会汇总到这里。"));
      return;
    }
    var groups = {};
    var order = [];
    data.forEach(function(group) {
      group.items.forEach(function(item) {
        var key = group.company + " · " + item.title;
        if (!groups[key]) { groups[key] = { company: group.company, title: item.title, items: [] }; order.push(key); }
        groups[key].items.push(item);
      });
    });
    order.forEach(function(key) { box.appendChild(reviewGroup(groups[key])); });
  } catch(e) {
    box.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

function reviewGroup(group) {
  return el("div", { class: "review-company-group" },
    el("div", { class: "review-company-header" },
      el("div", { class: "company-avatar" }, group.company.charAt(0)),
      el("div", {},
        el("h3", {}, group.company),
        el("div", { class: "muted text-sm" }, group.title + " · " + group.items.length + " 条记录")
      )
    ),
    el("div", { class: "review-items" },
      ...group.items.map(function(item) { return reviewCard(item); })
    )
  );
}

function reviewCard(item) {
  return el("div", { class: "review-card" },
    el("div", { class: "review-card-header" },
      el("div", { class: "review-card-title" },
        el("span", { class: "chip sm" }, item.stage),
        el("span", { class: "bold" }, item.title)
      ),
      el("div", { class: "review-card-meta muted text-sm" },
        item.scheduled_at ? el("span", {}, item.scheduled_at.slice(0, 10)) : null,
        item.form ? el("span", {}, item.form) : null,
        item.location ? el("span", {}, item.location) : null
      )
    ),
    el("div", { class: "review-card-body" },
      el("div", { class: "review-content", style: "white-space:pre-wrap" }, item.feedback)
    ),
    item.notes ? el("div", { class: "review-card-notes" },
      el("span", { class: "muted text-sm" }, "备注: " + item.notes)
    ) : null
  );
}
