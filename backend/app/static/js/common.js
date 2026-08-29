// === 通用请求 ===
function _authHeader() {
  var user = JSON.parse(localStorage.getItem("user") || "null");
  if (!user) return {};
  var headers = { "Authorization": "Bearer " + user.token };
  var groupId = localStorage.getItem("activeGroupId") || user.active_group_id;
  if (groupId) headers["X-Group-Id"] = String(groupId);
  return headers;
}

function getActiveGroupId() {
  return Number(localStorage.getItem("activeGroupId") || (currentUser && currentUser.active_group_id) || 0);
}

function setActiveGroupId(groupId) {
  localStorage.setItem("activeGroupId", String(groupId));
  if (currentUser) {
    currentUser.active_group_id = Number(groupId);
    localStorage.setItem("user", JSON.stringify(currentUser));
  }
}

async function _parseResponse(r, url) {
  if (r.ok) return r.json();
  if (r.status === 401 && !["/api/auth/login", "/api/auth/register"].includes(url || "")) {
    localStorage.removeItem("user");
    if (typeof showAuthPage === "function") showAuthPage();
  }
  throw new Error(await r.text());
}

const API = {
  async get(url) {
    const r = await fetch(url, { headers: _authHeader() });
    return _parseResponse(r, url);
  },
  async post(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, _authHeader()),
      body: body ? JSON.stringify(body) : undefined,
    });
    return _parseResponse(r, url);
  },
  async patch(url, body) {
    const r = await fetch(url, {
      method: "PATCH",
      headers: Object.assign({ "Content-Type": "application/json" }, _authHeader()),
      body: body ? JSON.stringify(body) : undefined,
    });
    return _parseResponse(r, url);
  },
  async del(url) {
    const r = await fetch(url, { method: "DELETE", headers: _authHeader() });
    return _parseResponse(r, url);
  },
  async upload(url, formData) {
    const r = await fetch(url, { method: "POST", body: formData, headers: _authHeader() });
    return _parseResponse(r, url);
  },
};

// === DOM 工具 ===
function el(tag, attrs, ...children) {
  const e = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "html") e.innerHTML = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, String(v));
    }
  }
  for (const c of children) {
    if (c == null || c === false) continue;
    if (typeof c === "string" || typeof c === "number") {
      e.appendChild(document.createTextNode(String(c)));
    } else if (c instanceof Node) {
      e.appendChild(c);
    }
  }
  return e;
}

function val(id) {
  const e = document.getElementById(id);
  return e ? e.value.trim() : "";
}

function formRow(label, input) {
  return el("div", { class: "form-row" }, el("label", {}, label), input);
}

function fmtDate(s) {
  if (!s) return "—";
  return s.slice(0, 10);
}

function daysLeft(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d - today) / 86400000);
}

function stageScheduleLabel(stageData) {
  if (!stageData) return "";
  if (stageData.schedule_type === "deadline" && stageData.deadline_at) {
    return "截止 " + stageData.deadline_at.slice(5, 16).replace("T", " ");
  }
  if (stageData.scheduled_at) {
    return stageData.scheduled_at.slice(5, 16).replace("T", " ");
  }
  return "";
}

function formatNotificationDays(item) {
  if (!item) return "—";
  if (item.days_left <= 0) return "今天";
  if (item.days_left === 1) return "明天";
  return item.days_left + "天";
}

function deadlineTag(dateStr) {
  if (!dateStr) return el("span", { class: "tag" }, "长期");
  const left = daysLeft(dateStr);
  if (left === null) return el("span", { class: "tag" }, "—");
  if (left < 0) return el("span", { class: "tag danger" }, "已截止");
  if (left <= 3) return el("span", { class: "tag danger" }, left + "天后截止");
  if (left <= 7) return el("span", { class: "tag warn" }, left + "天后截止");
  return el("span", { class: "tag" }, left + "天后截止");
}

function emptyState(text) {
  return el("div", { class: "empty" },
    el("div", { class: "icon" }, "📭"),
    el("div", {}, text),
  );
}

// === 导航切换 ===
var _renderedPages = {};

function invalidatePages() {
  _renderedPages = {};
}

function showPage(name, force) {
  document.querySelectorAll(".page").forEach(function(p) { p.classList.remove("active"); });
  document.querySelectorAll(".nav-item").forEach(function(n) { n.classList.remove("active"); });
  var page = document.getElementById("page-" + name);
  if (page) page.classList.add("active");
  var nav = document.querySelector('.nav-item[data-page="' + name + '"]');
  if (nav) nav.classList.add("active");
  if (!force && _renderedPages[name] && page && page.childElementCount) return;
  _renderedPages[name] = true;
  if (window["load_" + name]) window["load_" + name]();
}

// === 模态框 ===
function showModal(title, contentNode, footerNodes, opts) {
  var mask = document.getElementById("modal-mask");
  mask.innerHTML = "";
  var modal = el("div", { class: "modal" + (opts && opts.sheet ? " sheet-modal" : "") },
    title
      ? el("h3", {},
          el("span", { class: "close", onclick: closeModal }, "×"),
          title
        )
      : null,
    contentNode
  );
  if (footerNodes && footerNodes.length) {
    modal.appendChild(el("div", { class: "modal-footer" }, ...footerNodes));
  }
  mask.appendChild(modal);
  mask.classList.add("show");
  if (opts && opts.sheet) mask.classList.add("sheet-mask");
  else mask.classList.remove("sheet-mask");
}

function closeModal() {
  var mask = document.getElementById("modal-mask");
  mask.classList.remove("show");
  mask.classList.remove("sheet-mask");
}

document.addEventListener("keydown", function(event) {
  if (event.key === "Escape") closeModal();
});

function toast(msg, type) {
  var t = el("div", { class: "toast" + (type ? " " + type : "") }, msg);
  document.body.appendChild(t);
  setTimeout(function() { t.remove(); }, 2500);
}
