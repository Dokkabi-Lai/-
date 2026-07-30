// 登录注册
var currentUser = null;
var isRegisterMode = false;

function initAuth() {
  var saved = localStorage.getItem("user");
  if (saved) {
    try {
      currentUser = JSON.parse(saved);
      showApp();
      return;
    } catch(e) {}
  }
  showAuthPage();
}

function showAuthPage() {
  document.getElementById("auth-page").style.display = "flex";
  document.getElementById("app-main").style.display = "none";

  document.getElementById("auth-login-btn").onclick = doAuth;
  document.getElementById("auth-toggle").onclick = function(e) {
    e.preventDefault();
    isRegisterMode = !isRegisterMode;
    document.getElementById("auth-nick").style.display = isRegisterMode ? "block" : "none";
    document.getElementById("auth-login-btn").textContent = isRegisterMode ? "注册" : "登录";
    document.getElementById("auth-toggle").textContent = isRegisterMode ? "登录" : "注册";
    document.querySelector(".auth-switch").firstChild.textContent = isRegisterMode ? "已有账号？" : "没有账号？";
  };

  // Enter 键提交
  document.getElementById("auth-pass").addEventListener("keydown", function(e) {
    if (e.key === "Enter") doAuth();
  });
}

async function doAuth() {
  var username = val("auth-user");
  var password = val("auth-pass");
  if (!username || !password) { toast("请填写用户名和密码"); return; }

  var url = isRegisterMode ? "/api/auth/register" : "/api/auth/login";
  var body = { username: username, password: password };
  if (isRegisterMode) body.nickname = val("auth-nick") || username;

  try {
    var data = await API.post(url, body);
    currentUser = data;
    localStorage.setItem("user", JSON.stringify(data));
    showApp();
    toast(isRegisterMode ? "注册成功" : "登录成功");
  } catch(e) {
    toast(e.message || "登录失败");
  }
}

function showApp() {
  document.getElementById("auth-page").style.display = "none";
  document.getElementById("app-main").style.display = "flex";
  var info = document.getElementById("user-info");
  if (info && currentUser) info.textContent = currentUser.nickname || currentUser.username;
  showPage("home");
}

function logout() {
  currentUser = null;
  localStorage.removeItem("user");
  showAuthPage();
}
