window.load_offers = async function() {
  var page = document.getElementById("page-offers");
  page.innerHTML = "";
  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "🎉 我的Offer" ),
      el("div", { class: "page-sub muted" }, "恭喜拿到的offer都在这里")
    )
  ));
  page.appendChild(el("div", { id: "offer-list" }, el("div", { class: "loading" }, "加载中…")));
  loadOffers();
};

async function loadOffers() {
  var box = document.getElementById("offer-list");
  if (!box) return;
  try {
    var data = await API.get("/api/applications/offers/list");
    box.innerHTML = "";
    if (!data.length) {
      box.appendChild(emptyState("还没有拿到offer，继续加油！"));
      return;
    }
    // 统计
    box.appendChild(el("div", { class: "offer-stats" },
      el("div", { class: "offer-stat-card" },
        el("div", { class: "offer-stat-num" }, data.length),
        el("div", { class: "offer-stat-label" }, "Offer数")
      )
    ));
    // 列表
    data.forEach(function(app) {
      box.appendChild(offerCard(app));
    });
  } catch(e) {
    box.innerHTML = '<div class="card">加载失败: ' + e.message + '</div>';
  }
}

function offerCard(app) {
  var offerStage = (app.stages || []).find(function(s) { return s.stage === "Offer"; });
  var offerDate = offerStage && offerStage.completed_at ? offerStage.completed_at.slice(0, 10) : "";
  return el("div", { class: "offer-card" },
    el("div", { class: "offer-card-header" },
      el("div", { class: "company-avatar lg" }, app.company.charAt(0)),
      el("div", { class: "offer-card-info" },
        el("div", { class: "offer-company" }, app.company),
        el("div", { class: "offer-title" }, app.title),
        el("div", { class: "offer-meta" },
          el("span", { class: "chip sm" }, "🎉 Offer"),
          offerDate ? el("span", { class: "text-sm muted" }, "拿offer时间: " + offerDate) : null,
          app.channel ? el("span", { class: "chip sm" }, app.channel) : null
        )
      ),
      el("div", { class: "offer-celebrate" }, "🎊")
    ),
    offerStage && offerStage.feedback ? el("div", { class: "offer-feedback" },
      el("div", { class: "text-sm muted" }, "Offer备注:" ),
      el("div", { style: "white-space:pre-wrap", class: "text-sm mt-4" }, offerStage.feedback)
    ) : null,
    el("div", { class: "offer-actions" },
      el("button", { class: "btn sm", onclick: function() { viewOfferDetail(app); } }, "查看详情"),
      el("button", { class: "btn sm danger", onclick: function() { deleteOffer(app.id); } }, "删除")
    )
  );
}

async function deleteOffer(appId) {
  if (!confirm("确认删除这个Offer记录？")) return;
  try {
    await API.del("/api/applications/" + appId);
    toast("已删除");
    loadOffers();
  } catch(e) { toast("删除失败: " + e.message); }
}

function viewOfferDetail(app) {
  var body = el("div", { class: "job-detail" },
    el("div", { class: "job-detail-header" },
      el("div", { class: "company-avatar lg" }, app.company.charAt(0)),
      el("div", {},
        el("h3", {}, "🎉 " + app.company),
        el("h4", { class: "muted" }, app.title)
      )
    ),
    el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "📋 完整流程"),
      ...((app.stages || []).map(function(s) {
        return el("div", { class: "offer-stage-row" },
          el("span", { class: "stage-dot " + (s.status === "completed" ? "completed" : "") }),
          el("span", { class: "bold" }, s.stage),
          s.completed_at ? el("span", { class: "muted text-sm" }, " " + s.completed_at.slice(0, 10)) : null,
          s.feedback ? el("div", { class: "text-sm muted", style: "margin-left:20px;white-space:pre-wrap" }, s.feedback) : null
        );
      }))
    )
  );
  showModal("Offer详情 · " + app.company, body, [
    el("button", { class: "btn", onclick: closeModal }, "关闭")
  ]);
}
