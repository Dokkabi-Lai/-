var groupState = { items: [], active: null };

async function initGroups() {
  try {
    var data = await API.get("/api/groups");
    groupState.items = data.items || [];
    var activeId = getActiveGroupId() || data.active_group_id;
    groupState.active = groupState.items.find(function(g) { return g.id === Number(activeId); }) || groupState.items[0] || null;
    if (groupState.active) setActiveGroupId(groupState.active.id);
    renderGroupSwitcher();
    handleInviteFromUrl();
  } catch (e) {
    console.warn("群组加载失败", e);
  }
}

function renderGroupSwitcher() {
  var targets = [
    document.getElementById("group-switcher"),
    document.getElementById("mobile-group-bar")
  ];
  targets.forEach(function(target) {
    if (!target || !groupState.active) return;
    target.innerHTML = "";
    target.appendChild(el("button", { class: "group-switch-button", onclick: openGroupHub },
      el("span", { class: "group-mark" }, groupState.active.name.charAt(0)),
      el("span", { class: "group-switch-copy" },
        el("small", {}, "当前协作空间"),
        el("strong", {}, groupState.active.name)
      ),
      el("span", { class: "group-chevron" }, "⌄")
    ));
  });
}

function openGroupHub() {
  var content = el("div", { class: "group-hub" },
    el("div", { class: "group-hub-head" },
      el("p", { class: "muted" }, "切换岗位库，投递记录仍只属于你"),
      el("button", { class: "btn primary sm", onclick: openCreateGroup }, "新建群组")
    ),
    el("div", { class: "group-list" },
      ...groupState.items.map(function(group) {
        return el("button", {
          class: "group-list-item" + (groupState.active && group.id === groupState.active.id ? " active" : ""),
          onclick: function() { switchGroup(group.id); }
        },
          el("span", { class: "group-mark" }, group.name.charAt(0)),
          el("span", { class: "group-list-copy" },
            el("strong", {}, group.name),
            el("small", {}, group.member_count + " 位成员 · " + (group.is_owner ? "群主" : "成员"))
          ),
          groupState.active && group.id === groupState.active.id ? el("span", { class: "group-current" }, "当前") : null
        );
      })
    )
  );
  if (groupState.active) {
    content.appendChild(el("div", { class: "group-hub-actions" },
      el("button", { class: "btn", onclick: showGroupMembers }, "查看成员"),
      groupState.active.is_owner ? el("button", { class: "btn", onclick: createInviteLink }, "邀请成员") : null,
      groupState.active.is_owner ? el("button", { class: "btn", onclick: openFeishuBinding }, "飞书设置") : null,
      !groupState.active.is_owner && !groupState.active.is_system
        ? el("button", { class: "btn danger", onclick: leaveCurrentGroup }, "退出群组")
        : null
    ));
  }
  showModal("我的群组", content, [el("button", { class: "btn", onclick: closeModal }, "关闭")]);
}

async function switchGroup(groupId) {
  try {
    await API.post("/api/groups/" + groupId + "/activate");
    setActiveGroupId(groupId);
    groupState.active = groupState.items.find(function(g) { return g.id === groupId; });
    renderGroupSwitcher();
    closeModal();
    toast("已切换到「" + groupState.active.name + "」", "success");
    var activePage = document.querySelector(".page.active");
    showPage(activePage ? activePage.id.replace("page-", "") : "home");
  } catch (e) {
    toast("切换失败：" + parseGroupError(e), "error");
  }
}

function openCreateGroup() {
  var content = el("div", {},
    formRow("群组名称", el("input", { class: "input", id: "new-group-name", maxlength: "100", placeholder: "例如：27 届数据求职小组" })),
    formRow("群组简介", el("textarea", { class: "textarea", id: "new-group-description", placeholder: "告诉成员这个岗位库用于什么方向" }))
  );
  showModal("新建协作群组", content, [
    el("button", { class: "btn primary", onclick: createGroup }, "创建"),
    el("button", { class: "btn", onclick: openGroupHub }, "返回")
  ]);
}

async function createGroup() {
  try {
    var group = await API.post("/api/groups", {
      name: val("new-group-name"),
      description: val("new-group-description")
    });
    setActiveGroupId(group.id);
    await initGroups();
    closeModal();
    toast("群组创建成功", "success");
    showPage("jobs");
  } catch (e) {
    toast("创建失败：" + parseGroupError(e), "error");
  }
}

async function createInviteLink() {
  try {
    var invite = await API.post("/api/groups/" + groupState.active.id + "/invites");
    var content = el("div", { class: "invite-card" },
      el("div", { class: "invite-symbol" }, "↗"),
      el("h3", {}, "邀请朋友加入 " + groupState.active.name),
      el("p", { class: "muted" }, "链接 7 天内有效，对方登录后确认加入。"),
      el("div", { class: "copy-link-row" },
        el("input", { class: "input", id: "invite-link-value", readonly: true, value: invite.url }),
        el("button", { class: "btn primary", onclick: function() { copyText(invite.url); } }, "复制")
      )
    );
    showModal("邀请链接", content, [el("button", { class: "btn", onclick: openGroupHub }, "返回")]);
  } catch (e) {
    toast("生成邀请失败：" + parseGroupError(e), "error");
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    var input = document.getElementById("invite-link-value");
    if (input) { input.select(); document.execCommand("copy"); }
  }
  toast("邀请链接已复制", "success");
}

async function showGroupMembers() {
  try {
    var members = await API.get("/api/groups/" + groupState.active.id + "/members");
    var content = el("div", { class: "member-list" },
      ...members.map(function(member) {
        return el("div", { class: "member-row" },
          renderUserAvatar(member, "sm"),
          el("div", { class: "member-copy" },
            el("strong", {}, member.nickname || member.email),
            el("span", {}, member.email)
          ),
          el("span", { class: "role-chip" }, member.role === "owner" ? "群主" : "成员"),
          groupState.active.is_owner && member.role !== "owner"
            ? el("button", { class: "icon-btn", title: "移出群组", onclick: function() { removeGroupMember(member.user_id); } }, "×")
            : null
        );
      })
    );
    showModal(groupState.active.name + " · 成员", content, [el("button", { class: "btn", onclick: openGroupHub }, "返回")]);
  } catch (e) {
    toast("成员加载失败", "error");
  }
}

async function removeGroupMember(userId) {
  if (!confirm("确定将这位成员移出群组吗？")) return;
  await API.del("/api/groups/" + groupState.active.id + "/members/" + userId);
  toast("成员已移出", "success");
  showGroupMembers();
  initGroups();
}

function openFeishuBinding() {
  var content = el("div", {},
    formRow("飞书表格链接", el("input", { class: "input", id: "group-feishu-url", value: "", placeholder: "https://xxx.feishu.cn/sheets/..." })),
    formRow("工作表 ID（可选）", el("input", { class: "input", id: "group-feishu-sheet", placeholder: "留空读取第一个工作表" })),
    el("label", { class: "chip-toggle" },
      el("input", { type: "checkbox", id: "group-feishu-auto", checked: groupState.active.feishu_sync_enabled ? true : null }),
      el("span", {}, "开启每日自动同步")
    ),
    el("p", { class: "form-help" }, "飞书 App ID 和 Secret 由网站管理员在部署环境中统一配置。")
  );
  showModal("绑定飞书岗位表", content, [
    el("button", { class: "btn primary", onclick: saveFeishuBinding }, "保存"),
    el("button", { class: "btn", onclick: openGroupHub }, "返回")
  ]);
}

async function saveFeishuBinding() {
  try {
    var body = { feishu_sync_enabled: document.getElementById("group-feishu-auto").checked };
    if (val("group-feishu-url")) body.feishu_spreadsheet_token = val("group-feishu-url");
    if (val("group-feishu-sheet")) body.feishu_sheet_id = val("group-feishu-sheet");
    await API.patch("/api/groups/" + groupState.active.id, body);
    await initGroups();
    closeModal();
    toast("飞书设置已保存", "success");
  } catch (e) {
    toast("保存失败：" + parseGroupError(e), "error");
  }
}

async function leaveCurrentGroup() {
  if (!confirm("退出后将看不到该群岗位，但历史投递仍会保留。确定退出吗？")) return;
  try {
    await API.post("/api/groups/" + groupState.active.id + "/leave");
    localStorage.removeItem("activeGroupId");
    await initGroups();
    closeModal();
    showPage("home");
  } catch (e) {
    toast(parseGroupError(e), "error");
  }
}

async function handleInviteFromUrl() {
  var params = new URLSearchParams(location.search);
  var token = params.get("invite");
  if (!token || window._handledInviteToken === token) return;
  window._handledInviteToken = token;
  try {
    var preview = await API.get("/api/invites/" + encodeURIComponent(token));
    var content = el("div", { class: "invite-preview" },
      el("div", { class: "group-mark lg" }, preview.group_name.charAt(0)),
      el("div", { class: "eyebrow" }, "GROUP INVITATION"),
      el("h2", {}, preview.group_name),
      el("p", {}, preview.description || "一起维护更及时的岗位库"),
      el("span", { class: "muted" }, preview.inviter + " 邀请你加入 · " + preview.member_count + " 位成员")
    );
    showModal("群组邀请", content, [
      el("button", { class: "btn primary", onclick: function() { acceptInvite(token); } }, "确认加入"),
      el("button", { class: "btn", onclick: closeModal }, "暂不加入")
    ]);
  } catch (e) {
    toast("邀请链接无效或已过期", "error");
  }
}

async function acceptInvite(token) {
  try {
    var group = await API.post("/api/invites/" + encodeURIComponent(token) + "/accept");
    setActiveGroupId(group.id);
    history.replaceState({}, "", location.pathname);
    await initGroups();
    closeModal();
    toast("已加入「" + group.name + "」", "success");
    showPage("jobs");
  } catch (e) {
    toast("加入失败：" + parseGroupError(e), "error");
  }
}

function parseGroupError(e) {
  var message = (e && e.message) || "未知错误";
  try { return JSON.parse(message).detail || message; } catch (_) { return message; }
}

function openMobileMore() {
  var content = el("div", { class: "mobile-more-grid" },
    el("button", { onclick: function() { closeModal(); showPage("review"); } }, "投递仪表盘"),
    el("button", { onclick: function() { closeModal(); showPage("offers"); } }, "Offer"),
    el("button", { onclick: function() { closeModal(); showPage("profile"); } }, "个人主页"),
    el("button", { onclick: function() { closeModal(); openGroupHub(); } }, "群组管理"),
    el("button", { onclick: logout }, "退出登录")
  );
  showModal("更多", content, [el("button", { class: "btn", onclick: closeModal }, "关闭")]);
}

