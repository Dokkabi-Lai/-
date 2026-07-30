// === 通用请求 ===
function _authHeader() {
  var user = JSON.parse(localStorage.getItem("user") || "null");
  return user ? { "Authorization": "Bearer " + user.token } : {};
}

const API = {
  async get(url) {
    const r = await fetch(url, { headers: _authHeader() });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: Object.assign({ "Content-Type": "application/json" }, _authHeader()),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async patch(url, body) {
    const r = await fetch(url, {
      method: "PATCH",
      headers: Object.assign({ "Content-Type": "application/json" }, _authHeader()),
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async del(url) {
    const r = await fetch(url, { method: "DELETE", headers: _authHeader() });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async upload(url, formData) {
    const r = await fetch(url, { method: "POST", body: formData, headers: _authHeader() });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
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
function showPage(name) {
  document.querySelectorAll(".page").forEach(function(p) { p.classList.remove("active"); });
  document.querySelectorAll(".nav-item").forEach(function(n) { n.classList.remove("active"); });
  var page = document.getElementById("page-" + name);
  if (page) page.classList.add("active");
  var nav = document.querySelector('.nav-item[data-page="' + name + '"]');
  if (nav) nav.classList.add("active");
  if (window["load_" + name]) window["load_" + name]();
}

// === 模态框 ===
function showModal(title, contentNode, footerNodes) {
  var mask = document.getElementById("modal-mask");
  mask.innerHTML = "";
  var modal = el("div", { class: "modal" },
    el("h3", {},
      el("span", { class: "close", onclick: function() { mask.classList.remove("show"); } }, "×"),
      title,
    ),
    contentNode,
  );
  if (footerNodes && footerNodes.length) {
    modal.appendChild(el("div", { class: "modal-footer" }, ...footerNodes));
  }
  mask.appendChild(modal);
  mask.classList.add("show");
}

function closeModal() {
  document.getElementById("modal-mask").classList.remove("show");
}

function toast(msg, type) {
  var t = el("div", { class: "toast" + (type ? " " + type : "") }, msg);
  document.body.appendChild(t);
  setTimeout(function() { t.remove(); }, 2500);
}
