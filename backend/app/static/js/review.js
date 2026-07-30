window.load_review = async function() {
  var page = document.getElementById("page-review");
  page.innerHTML = "";
  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "面试复盘"),
      el("div", { class: "page-sub muted" }, "按公司整理所有面试反馈，帮助总结提升")
    )
  ));
  page.appendChild(el("div", { id: "review-list" }, el("div", { class: "loading" }, "加载中…")));
  loadReviews();
};

async function loadReviews() {
  var box = document.getElementById("review-list");
  if (!box) return;
  try {
    var data = await API.get("/api/applications/reviews/all");
    box.innerHTML = "";
    if (!data.length) {
      box.appendChild(emptyState("暂无复盘记录。在投递跟踪中编辑各阶段的「面试反馈」即可自动汇总到这里。"));
      return;
    }

    // 按 公司+岗位 分组
    var groups = {};
    var order = [];
    data.forEach(function(group) {
      group.items.forEach(function(item) {
        var key = group.company + " · " + item.title;
        if (!groups[key]) { groups[key] = { company: group.company, title: item.title, items: [] }; order.push(key); }
        groups[key].items.push(item);
      });
    });

    order.forEach(function(key) {
      box.appendChild(reviewGroup(groups[key]));
    });
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
        el("div", { class: "muted text-sm" }, group.title + " · " + group.items.length + " 条复盘")
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
        item.scheduled_at ? el("span", {}, "📅 " + item.scheduled_at.slice(0, 10)) : null,
        item.form ? el("span", {}, "📍 " + item.form) : null,
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
