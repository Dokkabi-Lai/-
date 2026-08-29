var currentUser = null;
var isRegisterMode = false;
var selectedAuthEmoji = "🌱";
var AVATAR_EMOJIS = ["🌱", "🎯", "🚀", "🍊", "🦊", "🐳", "🌻", "🪐", "🧭", "💡", "📚", "☕", "🚗", "🌧️"];

function initAuth() {
  var saved = localStorage.getItem("user");
  if (saved) {
    try {
      currentUser = JSON.parse(saved);
      if (currentUser && currentUser.token) {
        API.get("/api/auth/me").then(function(data) {
          saveCurrentUser(data);
          showApp();
        }).catch(function() {
          localStorage.removeItem("user");
          currentUser = null;
          showAuthPage();
        });
        return;
      }
    } catch (e) {}
  }
  showAuthPage();
}

function showAuthPage() {
  var auth = document.getElementById("auth-page");
  var app = document.getElementById("app-main");
  if (auth) auth.style.display = "flex";
  if (app) app.style.display = "none";
  bindAuthForm();
}

function bindAuthForm() {
  var btn = document.getElementById("auth-submit");
  var toggle = document.getElementById("auth-toggle");
  if (btn) btn.onclick = submitAuth;
  if (toggle) toggle.onclick = function(e) {
    e.preventDefault();
    isRegisterMode = !isRegisterMode;
    syncAuthMode();
  };
  var pass = document.getElementById("auth-pass");
  if (pass) pass.onkeydown = function(e) { if (e.key === "Enter") submitAuth(); };
  renderAuthAvatarPicker();
  syncAuthMode();
}

function syncAuthMode() {
  var fields = document.getElementById("auth-register-fields");
  var btn = document.getElementById("auth-submit");
  var toggle = document.getElementById("auth-toggle");
  var hint = document.getElementById("auth-switch-hint");
  if (fields) fields.style.display = isRegisterMode ? "block" : "none";
  if (btn) btn.textContent = isRegisterMode ? "注册并进入" : "登录";
  if (toggle) toggle.textContent = isRegisterMode ? "去登录" : "去注册";
  if (hint) hint.textContent = isRegisterMode ? "已有账号？" : "还没有账号？";
}

function renderAuthAvatarPicker() {
  var picker = document.getElementById("auth-avatar-picker");
  if (!picker || picker.childElementCount) return;
  picker.appendChild(el("div", { class: "auth-avatar-label" }, "选一个代表你的头像"));
  var grid = el("div", { class: "emoji-grid compact" });
  AVATAR_EMOJIS.forEach(function(emoji) {
    grid.appendChild(el("button", {
      type: "button",
      class: "emoji-option" + (emoji === selectedAuthEmoji ? " selected" : ""),
      onclick: function() {
        selectedAuthEmoji = emoji;
        grid.querySelectorAll(".emoji-option").forEach(function(button) {
          button.classList.toggle("selected", button.textContent === emoji);
        });
      }
    }, emoji));
  });
  picker.appendChild(grid);
}

async function submitAuth() {
  var email = val("auth-email");
  var password = val("auth-pass");
  if (!email || !password) { toast("请填写邮箱和密码"); return; }
  if (isRegisterMode && password.length < 8) { toast("密码至少 8 位"); return; }
  var url = isRegisterMode ? "/api/auth/register" : "/api/auth/login";
  var body = { email: email, password: password };
  if (isRegisterMode) {
    body.nickname = val("auth-nick") || email.split("@")[0];
    body.avatar_emoji = selectedAuthEmoji;
  }
  try {
    var data = await API.post(url, body);
    currentUser = data;
    localStorage.setItem("user", JSON.stringify(data));
    if (data.active_group_id) setActiveGroupId(data.active_group_id);
    showApp();
    toast(isRegisterMode ? "注册成功" : "登录成功");
  } catch (e) {
    toast(_authError(e));
  }
}

function showApp() {
  var auth = document.getElementById("auth-page");
  var app = document.getElementById("app-main");
  if (auth) auth.style.display = "none";
  if (app) app.style.display = "flex";
  renderSidebarUser();
  if (typeof initGroups === "function") initGroups();
  showPage("home");
}

function renderSidebarUser() {
  var info = document.getElementById("user-info");
  if (!info || !currentUser) return;
  info.innerHTML = "";
  info.appendChild(renderUserAvatar(currentUser, "sm"));
  info.appendChild(el("div", { class: "user-card-copy" },
    el("strong", {}, currentUser.nickname || currentUser.email || "已登录"),
    el("span", {}, currentUser.email || "查看个人主页")
  ));
  info.appendChild(el("span", { class: "user-card-arrow" }, "›"));
}

function renderUserAvatar(user, sizeClass) {
  var className = "user-avatar" + (sizeClass ? " " + sizeClass : "");
  if (user && user.avatar_type === "upload" && user.avatar_url) {
    return el("img", { class: className, src: user.avatar_url, alt: "用户头像" });
  }
  return el("span", { class: className + " emoji" }, (user && user.avatar_emoji) || "🌱");
}

function saveCurrentUser(data) {
  var token = currentUser && currentUser.token;
  currentUser = Object.assign({}, data, token ? { token: token } : {});
  localStorage.setItem("user", JSON.stringify(currentUser));
  if (data.active_group_id) setActiveGroupId(data.active_group_id);
  renderSidebarUser();
}

function logout() {
  currentUser = null;
  localStorage.removeItem("user");
  localStorage.removeItem("activeGroupId");
  showAuthPage();
}

function _authError(e) {
  var msg = (e && e.message) || "失败";
  try {
    var j = JSON.parse(msg);
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail) && j.detail[0]) return j.detail[0].msg || msg;
  } catch (x) {}
  return msg;
}
