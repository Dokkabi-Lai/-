window.load_profile = async function() {
  var page = document.getElementById("page-profile");
  page.innerHTML = '<div class="loading skeleton-block"></div>';
  try {
    var results = await Promise.all([
      API.get("/api/auth/me"),
      API.get("/api/applications/dashboard")
    ]);
    saveCurrentUser(results[0]);
    renderProfile(page, results[0], results[1]);
  } catch (e) {
    page.innerHTML = "";
    page.appendChild(emptyState("个人资料加载失败"));
  }
};

function renderProfile(page, user, stats) {
  page.innerHTML = "";
  var hero = el("section", { class: "profile-hero" },
    el("div", { class: "profile-avatar-wrap" },
      renderUserAvatar(user, "xl"),
      el("button", { class: "avatar-edit-btn", onclick: openAvatarPicker, title: "更换头像" }, "✦")
    ),
    el("div", { class: "profile-identity" },
      el("div", { class: "eyebrow" }, "MY AUTUMN JOURNEY"),
      el("h1", {}, user.nickname || "未命名用户"),
      el("button", { class: "manifesto-display", onclick: editManifesto },
        el("span", {}, user.bio || "写下一句属于你的求职宣言。"),
        el("small", {}, "点击更换")
      ),
      el("div", { class: "profile-meta" },
        user.school ? el("span", {}, user.school) : null,
        user.major ? el("span", {}, user.major) : null,
        user.graduation_year ? el("span", {}, user.graduation_year + " 届") : null,
        user.is_admin ? el("span", { class: "admin-badge" }, "管理员") : null
      )
    ),
    el("button", { class: "btn soft", onclick: editManifesto }, "更换宣言")
  );
  page.appendChild(hero);

  var status = stats.by_status || {};
  page.appendChild(el("div", { class: "profile-stat-grid" },
    profileStat(stats.total || 0, "累计投递", "从第一份勇气开始"),
    profileStat(status["进行中"] || 0, "正在推进", "保持节奏"),
    profileStat(status["已完成"] || 0, "收获 Offer", "每一步都有回声"),
    profileStat((user.target_roles || []).length, "目标方向", "让选择更聚焦")
  ));

  var form = el("div", { class: "profile-layout" },
    el("section", { class: "card profile-form-card" },
      el("div", { class: "section-heading" },
        el("div", {}, el("span", { class: "eyebrow" }, "PROFILE"), el("h2", {}, "我的信息")),
        el("span", { class: "muted text-sm" }, "邮箱 " + user.email)
      ),
      el("div", { class: "profile-form-grid" },
        profileInput("昵称", "profile-nickname", user.nickname || "", "怎么称呼你"),
        profileInput("学校", "profile-school", user.school || "", "学校名称"),
        profileInput("专业", "profile-major", user.major || "", "所学专业"),
        profileInput("毕业年份", "profile-year", user.graduation_year || "", "例如 2027", "number"),
        profileInput("目标岗位", "profile-roles", (user.target_roles || []).join("、"), "数据分析、产品、运营"),
        profileInput("目标城市", "profile-cities", (user.target_cities || []).join("、"), "上海、杭州、深圳")
      ),
      formRow("个人简介", el("textarea", {
        class: "textarea profile-bio",
        id: "profile-bio",
        maxlength: "500",
        placeholder: "记录你正在寻找怎样的机会…"
      }, user.bio || "")),
      el("div", { class: "profile-actions" },
        el("button", { class: "btn primary", onclick: saveProfile }, "保存个人资料")
      )
    ),
    el("aside", { class: "card profile-note" },
      el("span", { class: "note-glyph" }, "“"),
      el("h3", {}, "今日小签"),
      el("p", {}, user.bio || "把目标拆成今天能完成的一小步。投递不是一次考试，而是一段不断校准方向的旅程。"),
      el("div", { class: "note-date" }, new Date().toLocaleDateString("zh-CN", { month: "long", day: "numeric" })),
      el("div", { class: "profile-quick-links" },
        el("button", { class: "btn", onclick: openGroupHub }, "群组管理"),
        el("button", { class: "btn danger", onclick: logout }, "退出登录")
      )
    )
  );
  page.appendChild(form);
}

function editManifesto() {
  var content = el("div", { class: "manifesto-editor" },
    el("p", { class: "muted" }, "一句真正属于你的话，会在首页和个人主页陪着你。"),
    el("textarea", {
      class: "textarea",
      id: "manifesto-input",
      maxlength: "500",
      placeholder: "例如：保持好奇，也保持行动。"
    }, (currentUser && currentUser.bio) || ""),
    el("div", { class: "form-help" }, "最多 500 字")
  );
  showModal("更换求职宣言", content, [
    el("button", { class: "btn primary", onclick: saveManifesto }, "保存宣言"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function saveManifesto() {
  try {
    var data = await API.patch("/api/auth/me", { bio: val("manifesto-input") });
    saveCurrentUser(data);
    closeModal();
    load_profile();
    toast("求职宣言已更新", "success");
  } catch (e) {
    toast("保存失败：" + parseProfileError(e), "error");
  }
}

function profileStat(value, label, hint) {
  return el("div", { class: "profile-stat" },
    el("strong", {}, value),
    el("span", {}, label),
    el("small", {}, hint)
  );
}

function profileInput(label, id, value, placeholder, type) {
  return formRow(label, el("input", {
    class: "input",
    id: id,
    type: type || "text",
    value: value,
    placeholder: placeholder
  }));
}

function splitProfileList(value) {
  return value.split(/[、,，]/).map(function(v) { return v.trim(); }).filter(Boolean);
}

async function saveProfile() {
  try {
    var data = await API.patch("/api/auth/me", {
      nickname: val("profile-nickname"),
      school: val("profile-school"),
      major: val("profile-major"),
      graduation_year: val("profile-year") || null,
      target_roles: splitProfileList(val("profile-roles")),
      target_cities: splitProfileList(val("profile-cities")),
      bio: val("profile-bio")
    });
    saveCurrentUser(data);
    toast("个人资料已保存", "success");
    load_profile();
  } catch (e) {
    toast("保存失败：" + parseProfileError(e), "error");
  }
}

function openAvatarPicker() {
  var preview = el("div", { class: "avatar-picker-panel" },
    el("p", { class: "muted" }, "选一个表情，或者上传自己的照片"),
    el("div", { class: "emoji-grid" },
      ...AVATAR_EMOJIS.map(function(emoji) {
        return el("button", {
          type: "button",
          class: "emoji-option" + (currentUser.avatar_emoji === emoji && currentUser.avatar_type !== "upload" ? " selected" : ""),
          onclick: function() { chooseProfileEmoji(emoji); }
        }, emoji);
      })
    ),
    el("div", { class: "avatar-upload-zone", onclick: function() { document.getElementById("profile-avatar-file").click(); } },
      el("strong", {}, "上传图片"),
      el("span", {}, "JPG / PNG / WebP / GIF，不超过 3MB"),
      el("input", {
        type: "file",
        id: "profile-avatar-file",
        accept: "image/jpeg,image/png,image/webp,image/gif",
        hidden: true,
        onchange: function(e) { uploadProfileAvatar(e.target.files[0]); }
      })
    )
  );
  showModal("更换头像", preview, [el("button", { class: "btn", onclick: closeModal }, "取消")]);
}

async function chooseProfileEmoji(emoji) {
  try {
    var data = await API.patch("/api/auth/me", { avatar_emoji: emoji });
    saveCurrentUser(data);
    closeModal();
    load_profile();
    toast("头像已更新", "success");
  } catch (e) {
    toast("头像更新失败", "error");
  }
}

async function uploadProfileAvatar(file) {
  if (!file) return;
  var fd = new FormData();
  fd.append("file", file);
  try {
    toast("正在上传头像…");
    var data = await API.upload("/api/auth/avatar", fd);
    saveCurrentUser(data);
    closeModal();
    load_profile();
    toast("头像已更新", "success");
  } catch (e) {
    toast("上传失败：" + parseProfileError(e), "error");
  }
}

function parseProfileError(e) {
  var message = (e && e.message) || "未知错误";
  try { return JSON.parse(message).detail || message; } catch (_) { return message; }
}

