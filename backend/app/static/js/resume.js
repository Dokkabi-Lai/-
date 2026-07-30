// 我的：简历 + 简历分析 + 问答偏好 + 大模型设置
window.load_resume = async function() {
  var page = document.getElementById("page-resume");
  page.innerHTML = "";
  page.appendChild(el("div", { class: "page-header" },
    el("div", {},
      el("h1", { class: "page-title" }, "个人中心"),
      el("div", { class: "page-sub muted" }, "简历管理、AI分析、求职偏好设置")
    )
  ));

  // 简历管理 + 分析
  page.appendChild(el("div", { class: "card" },
    el("div", { class: "card-header" },
      el("h3", { class: "card-title" }, "📄 简历管理"),
      el("div", { class: "header-actions" },
        el("input", { type: "file", id: "resume-file", accept: ".pdf,.docx,.doc,.txt", style: "display:none" }),
        el("button", { class: "btn sm", onclick: function() { document.getElementById("resume-file").click(); } }, "📤 上传文件"),
        el("button", { class: "btn sm", onclick: function() { showManualResume(); } }, "✍️ 手动填写")
      )
    ),
    el("div", { id: "resume-list", class: "loading" }, "加载中…")
  ));

  // 简历分析结果
  page.appendChild(el("div", { class: "card", id: "analysis-card", style: "display:none" },
    el("div", { class: "card-header" },
      el("h3", { class: "card-title" }, "🤖 AI简历分析"),
      el("button", { class: "btn sm", onclick: function() { rerunAnalysis(); } }, "🔄 重新分析")
    ),
    el("div", { id: "analysis-result" })
  ));

  // 求职偏好
  page.appendChild(el("div", { class: "card" },
    el("div", { class: "card-header" },
      el("h3", { class: "card-title" }, "🎯 求职偏好")
    ),
    el("div", { id: "pref-form", class: "loading" }, "加载中…")
  ));

  // 大模型设置
  page.appendChild(el("div", { class: "card" },
    el("div", { class: "card-header" },
      el("h3", { class: "card-title" }, "🤖 大模型设置")
    ),
    el("div", { id: "llm-status" })
  ));

  // 推送与日历
  page.appendChild(el("div", { class: "card" },
    el("div", { class: "card-header" },
      el("h3", { class: "card-title" }, "🔔 推送与日历")
    ),
    el("div", { class: "muted text-sm mb-16" }, "每日早上 8:00 自动推送今日待办。可手动同步到系统日历。"),
    el("div", { class: "flex gap-8" },
      el("button", { class: "btn sm", onclick: function() { testNotify(); } }, "测试通知"),
      el("button", { class: "btn sm", onclick: function() { dailyPush(); } }, "立即推送"),
      el("button", { class: "btn sm primary", onclick: function() { syncCalendar(); } }, "同步到日历")
    ),
    el("div", { id: "notify-result", class: "mt-12" })
  ));

  loadResumes();
  loadPreference();
  loadLLMStatus();
  document.getElementById("resume-file").onchange = uploadResume;
};

// === 简历管理 ===
async function loadResumes() {
  var box = document.getElementById("resume-list");
  try {
    var data = await API.get("/api/resume/list");
    box.innerHTML = "";
    if (!data.length) {
      box.appendChild(el("div", { class: "empty-mini" }, "暂无简历，上传文件或手动填写开始"));
      return;
    }
    data.forEach(function(r) {
      var item = el("div", { class: "list-item" },
        el("div", { class: "main-info" },
          el("div", { class: "title" },
            r.name,
            r.is_default ? el("span", { class: "tag primary", style: "margin-left:8px" }, "默认") : null
          ),
          el("div", { class: "sub" }, r.has_text ? "已有内容" : "无内容")
        ),
        el("div", { class: "actions" },
          el("button", { class: "btn sm primary", onclick: function() { analyzeResume(r.id); } }, "🤖 AI分析"),
          el("button", { class: "btn sm", onclick: function() { editResumeText(r); } }, "编辑"),
          r.is_default ? null : el("button", { class: "btn sm", onclick: function() { setDefaultResume(r.id); } }, "设为默认"),
          el("button", { class: "btn sm danger", onclick: function() { delResume(r.id); } }, "删除")
        )
      );
      box.appendChild(item);
      // 如果有结构化数据，显示分析结果
      if (r.is_default && r.structured) {
        showAnalysisResult(r.structured);
      }
    });
  } catch(e) { box.innerHTML = "加载失败: " + e.message; }
}

function showManualResume() {
  var body = el("div", {},
    formRow("简历名称", el("input", { class: "input", id: "mr-name", placeholder: "如: 后端开发简历" })),
    formRow("简历内容", el("textarea", { class: "textarea", style: "min-height:300px", id: "mr-text", placeholder: "填写你的简历内容：\n\n姓名：\n联系方式：\n教育背景：\n技能：\n项目经历：\n实习经历：\n获奖：\n自我评价：" }))
  );
  showModal("手动填写简历", body, [
    el("button", { class: "btn primary", onclick: function() { submitManualResume(); } }, "保存"),
    el("button", { class: "btn", onclick: closeModal }, "取消")
  ]);
}

async function submitManualResume() {
  var name = val("mr-name") || "手动简历";
  var text = val("mr-text");
  if (!text.trim()) { toast("请填写简历内容"); return; }
  try {
    await API.post("/api/resume/manual", { name: name, raw_text: text });
    toast("简历已保存");
    closeModal();
    loadResumes();
  } catch(e) { toast("保存失败: " + e.message); }
}

async function editResumeText(r) {
  try {
    var data = await API.get("/api/resume/" + r.id + "/text");
    var body = el("div", {},
      formRow("简历名称", el("input", { class: "input", id: "er-name", value: data.name })),
      formRow("简历内容", el("textarea", { class: "textarea", style: "min-height:300px", id: "er-text" }, data.raw_text || ""))
    );
    showModal("编辑简历", body, [
      el("button", { class: "btn primary", onclick: async function() {
        await API.patch("/api/resume/" + r.id + "/text", { name: val("er-name"), raw_text: val("er-text") });
        toast("已保存"); closeModal(); loadResumes();
      } }, "保存"),
      el("button", { class: "btn", onclick: closeModal }, "取消")
    ]);
  } catch(e) { toast("加载失败: " + e.message); }
}

async function uploadResume() {
  var input = document.getElementById("resume-file");
  if (!input.files.length) return;
  var fd = new FormData();
  fd.append("file", input.files[0]);
  fd.append("name", input.files[0].name.replace(/\.[^.]+$/, ""));
  toast("上传解析中…");
  try {
    await API.upload("/api/resume/upload", fd);
    toast("上传成功");
    loadResumes();
  } catch(e) { toast("上传失败: " + e.message); }
  input.value = "";
}

async function setDefaultResume(id) {
  await API.post("/api/resume/" + id + "/default");
  loadResumes();
}

async function delResume(id) {
  if (!confirm("确认删除？")) return;
  await API.del("/api/resume/" + id);
  loadResumes();
}

// === AI简历分析 ===
async function analyzeResume(id) {
  toast("🤖 AI分析中…");
  try {
    var result = await API.post("/api/resume/" + id + "/analyze", {});
    toast("分析完成！");
    showAnalysisResult(result);
  } catch(e) {
    toast("分析失败: " + e.message);
  }
}

async function rerunAnalysis() {
  var resumes = await API.get("/api/resume/list");
  var def = resumes.find(function(r) { return r.is_default; });
  if (def) analyzeResume(def.id);
}

function showAnalysisResult(r) {
  var card = document.getElementById("analysis-card");
  var box = document.getElementById("analysis-result");
  if (!card || !box) return;
  card.style.display = "block";
  box.innerHTML = "";

  // 总体评价
  box.appendChild(el("div", { class: "analysis-summary" },
    el("div", { class: "bold", style: "font-size:15px" }, r.summary || "")
  ));

  // 市场竞争力 + 薪资期望
  var marketInfo = el("div", { class: "detail-section", style: "display:flex;gap:12px;flex-wrap:wrap" });
  if (r.market_competitiveness) {
    marketInfo.appendChild(el("div", { class: "chip", style: "background:rgba(0,122,255,0.1);color:#007aff" }, "📊 " + r.market_competitiveness));
  }
  if (r.salary_expectation) {
    marketInfo.appendChild(el("div", { class: "chip", style: "background:rgba(52,199,89,0.1);color:#34c759" }, "💰 期望薪资: " + r.salary_expectation));
  }
  if (r.career_direction) {
    marketInfo.appendChild(el("div", { class: "chip", style: "background:rgba(88,86,214,0.1);color:#5856d6" }, "🧭 " + r.career_direction));
  }
  if (marketInfo.children.length) box.appendChild(marketInfo);

  // 技能分析（新格式：对象数组）
  if (r.skill_analysis && r.skill_analysis.length) {
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "🛠 技能分析"),
      ...r.skill_analysis.map(function(s) {
        var levelColor = s.level === "精通" ? "var(--green)" : s.level === "熟悉" ? "var(--blue)" : "var(--text-tertiary)";
        return el("div", { class: "skill-row" },
          el("span", { class: "chip", style: "background:" + levelColor + "20;color:" + levelColor }, s.skill + " · " + (s.level || "")),
          s.evidence ? el("span", { class: "text-sm muted", style: "margin-left:8px" }, s.evidence) : null
        );
      })
    ));
  } else if (r.skills && r.skills.length) {
    // 兼容旧格式
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "🛠 技能"),
      el("div", { class: "tag-list" },
        ...r.skills.map(function(s) { return el("span", { class: "chip" }, s); })
      )
    ));
  }

  // 学历详情
  if (r.education_detail || r.education) {
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "🎓 学历"),
      el("div", {}, r.education_detail || r.education)
    ));
  }

  // 项目经历（新格式：对象数组）
  if (r.projects && r.projects.length) {
    var isObj = typeof r.projects[0] === "object";
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "📦 项目经历"),
      ...r.projects.map(function(p) {
        if (isObj) {
          return el("div", { class: "project-card" },
            el("div", { class: "bold" }, p.name + (p.role ? " · " + p.role : "")),
            p.description ? el("div", { class: "text-sm muted" }, p.description) : null,
            p.highlights && p.highlights.length ? el("div", { class: "text-sm", style: "margin-top:4px" },
              ...p.highlights.map(function(h) { return el("div", {}, "✨ " + h); })
            ) : null,
            p.tech_stack && p.tech_stack.length ? el("div", { class: "tag-list", style: "margin-top:4px" },
              ...p.tech_stack.map(function(t) { return el("span", { class: "chip sm" }, t); })
            ) : null
          );
        }
        return el("div", { class: "text-sm", style: "margin-bottom:4px" }, "· " + p);
      })
    ));
  }

  // 实习经历
  if (r.internships && r.internships.length) {
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "🏢 实习经历"),
      ...r.internships.map(function(i) {
        return el("div", { class: "project-card" },
          el("div", { class: "bold" }, (i.company || "") + (i.role ? " · " + i.role : "") + (i.duration ? " (" + i.duration + ")" : "")),
          i.description ? el("div", { class: "text-sm muted" }, i.description) : null
        );
      })
    ));
  }

  // 优势（新格式：对象数组）
  if (r.strengths && r.strengths.length) {
    var isObjS = typeof r.strengths[0] === "object";
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "💪 优势"),
      ...r.strengths.map(function(s) {
        if (isObjS) {
          return el("div", { class: "text-sm", style: "margin-bottom:6px" },
            el("div", { style: "color:var(--green);font-weight:500" }, "✅ " + s.point),
            s.evidence ? el("div", { class: "muted", style: "margin-left:16px" }, "依据: " + s.evidence) : null,
            s.impact ? el("div", { class: "muted", style: "margin-left:16px" }, "影响: " + s.impact) : null
          );
        }
        return el("div", { class: "text-sm", style: "color:var(--green)" }, "✅ " + s);
      })
    ));
  }

  // 不足（新格式：对象数组）
  if (r.weaknesses && r.weaknesses.length) {
    var isObjW = typeof r.weaknesses[0] === "object";
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "⚠️ 不足"),
      ...r.weaknesses.map(function(s) {
        if (isObjW) {
          return el("div", { class: "text-sm", style: "margin-bottom:6px" },
            el("div", { style: "color:var(--orange);font-weight:500" }, "· " + s.point),
            s.suggestion ? el("div", { class: "muted", style: "margin-left:16px" }, "建议: " + s.suggestion) : null
          );
        }
        return el("div", { class: "text-sm", style: "color:var(--orange)" }, "· " + s);
      })
    ));
  }

  // 适合的岗位
  if (r.suitable_roles && r.suitable_roles.length) {
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "🎯 适合的岗位"),
      el("div", { class: "tag-list" },
        ...r.suitable_roles.map(function(s) { return el("span", { class: "chip primary" }, s); })
      )
    ));
  }

  // 推荐投递职位（可编辑）
  (function() {
    var positions = (r.recommended_positions && r.recommended_positions.length) ? r.recommended_positions.slice() : [];
    var section = el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "📋 推荐投递职位（可编辑）")
    );
    var tagList = el("div", { class: "tag-list", id: "rec-pos-tags" });

    function renderTags() {
      tagList.innerHTML = "";
      positions.forEach(function(pos, idx) {
        var chip = el("span", { class: "chip primary", style: "display:inline-flex;align-items:center;gap:4px" },
          pos,
          el("span", {
            style: "cursor:pointer;margin-left:4px;font-weight:bold;color:var(--danger,#e74c3c)",
            onclick: function(e) {
              e.stopPropagation();
              positions.splice(idx, 1);
              renderTags();
            }
          }, "×")
        );
        tagList.appendChild(chip);
      });
    }
    renderTags();

    var addInput = el("input", {
      class: "input",
      placeholder: "添加职位，回车确认",
      style: "width:200px;margin-top:8px"
    });
    addInput.addEventListener("keydown", function(e) {
      if (e.key === "Enter" && this.value.trim()) {
        e.preventDefault();
        positions.push(this.value.trim());
        this.value = "";
        renderTags();
      }
    });

    var saveBtn = el("button", {
      class: "btn sm primary",
      style: "margin-top:8px;margin-left:8px",
      onclick: async function() {
        try {
          await API.post("/api/resume/analysis/positions", { positions: positions });
          toast("推荐投递职位已保存");
        } catch(e) {
          toast("保存失败: " + e.message);
        }
      }
    }, "保存");

    var inputRow = el("div", { style: "display:flex;align-items:center;flex-wrap:wrap" }, addInput, saveBtn);
    section.appendChild(tagList);
    section.appendChild(inputRow);
    box.appendChild(section);
  })();

  if (r.improvement_suggestions && r.improvement_suggestions.length) {
    var isObjI = typeof r.improvement_suggestions[0] === "object";
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "💡 改进建议"),
      ...r.improvement_suggestions.map(function(s) {
        if (isObjI) {
          var pColor = s.priority === "高" ? "var(--red)" : s.priority === "中" ? "var(--orange)" : "var(--text-tertiary)";
          return el("div", { class: "text-sm", style: "margin-bottom:8px" },
            el("div", {},
              el("span", { class: "chip sm", style: "background:" + pColor + "20;color:" + pColor + ";margin-right:6px" }, s.priority || "中"),
              el("span", { class: "bold" }, s.aspect || "")
            ),
            s.current ? el("div", { class: "muted", style: "margin-left:4px;margin-top:2px" }, "当前: " + s.current) : null,
            s.suggestion ? el("div", { style: "margin-left:4px;margin-top:2px" }, "建议: " + s.suggestion) : null
          );
        }
        return el("div", { class: "text-sm" }, "· " + s);
      })
    ));
  }

  // 面试准备建议
  if (r.interview_prep && r.interview_prep.length) {
    box.appendChild(el("div", { class: "detail-section" },
      el("h5", { class: "detail-section-title" }, "🎤 面试准备建议"),
      ...r.interview_prep.map(function(q) { return el("div", { class: "text-sm", style: "margin-bottom:4px" }, "❓ " + q); })
    ));
  }
}

// === 求职偏好（标签多选） ===
var LOCATION_OPTIONS = ["北京","上海","广州","深圳","杭州","成都","南京","武汉","西安","苏州"];
var JOB_TYPE_OPTIONS = ["后端开发","前端开发","全栈开发","算法工程师","数据分析","产品经理","运营","测试","嵌入式","硬件"];
var INDUSTRY_OPTIONS = ["互联网","金融","制造","教育","医疗","游戏","通信","汽车","半导体","新能源"];

function tagSelector(id, label, options, selected) {
  var selectedSet = new Set(selected || []);
  var container = el("div", { class: "form-row" });
  container.appendChild(el("label", {}, label));
  var tagsDiv = el("div", { class: "tag-selector", id: id });
  options.forEach(function(opt) {
    var isSelected = selectedSet.has(opt);
    var tag = el("div", {
      class: "tag-option" + (isSelected ? " selected" : ""),
      onclick: function() { this.classList.toggle("selected"); }
    }, opt);
    tagsDiv.appendChild(tag);
  });
  var customInput = el("input", {
    class: "input tag-custom-input",
    placeholder: "其他（回车添加）",
    style: "width:120px;margin-top:6px"
  });
  customInput.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && this.value.trim()) {
      e.preventDefault();
      var v = this.value.trim();
      var tag = el("div", { class: "tag-option selected", onclick: function() { this.classList.toggle("selected"); } }, v);
      tagsDiv.insertBefore(tag, tagsDiv.lastChild);
      this.value = "";
    }
  });
  tagsDiv.appendChild(customInput);
  container.appendChild(tagsDiv);
  return container;
}

function getSelectedTags(id) {
  var tags = document.querySelectorAll("#" + id + " .tag-option.selected");
  return Array.from(tags).map(function(t) { return t.textContent; });
}

async function loadPreference() {
  var box = document.getElementById("pref-form");
  try {
    var p = await API.get("/api/resume/preference");
    box.innerHTML = "";
    box.appendChild(tagSelector("p-loc", "期望地区", LOCATION_OPTIONS, p.desired_locations));
    box.appendChild(tagSelector("p-job", "期望岗位", JOB_TYPE_OPTIONS, p.desired_job_types));
    box.appendChild(tagSelector("p-ind", "期望行业", INDUSTRY_OPTIONS, p.desired_industries));
    box.appendChild(formRow("最低薪资(K)", el("input", { class: "input", id: "p-sal", type: "number", value: p.min_salary || "" })));
    box.appendChild(el("div", { class: "mt-16" },
      el("button", { class: "btn primary", onclick: function() { savePreference(); } }, "保存偏好")
    ));
  } catch(e) { box.innerHTML = "加载失败: " + e.message; }
}

async function savePreference() {
  var data = {
    desired_locations: getSelectedTags("p-loc"),
    desired_job_types: getSelectedTags("p-job"),
    desired_industries: getSelectedTags("p-ind"),
    min_salary: val("p-sal") ? parseInt(val("p-sal")) : null
  };
  await API.post("/api/resume/preference", data);
  toast("偏好已保存，首页推荐将更新");
}

// === AI问答式偏好设置 ===
var _chatMessages = [];

function showChatPreference() {
  _chatMessages = [];
  var body = el("div", { class: "chat-container" },
    el("div", { class: "chat-messages", id: "chat-messages" },
      el("div", { class: "chat-bubble ai" },
        el("div", { class: "chat-text" }, "你好！我来帮你快速设置求职偏好。先问一下，你想在哪些城市工作？")
      )
    ),
    el("div", { class: "chat-input-area" },
      el("input", { class: "input", id: "chat-input", placeholder: "输入你的回答...", onkeydown: function(e) { if (e.key === "Enter") sendChatMessage(); } }),
      el("button", { class: "btn primary", onclick: function() { sendChatMessage(); } }, "发送")
    )
  );
  showModal("💬 AI问答设置偏好", body, [
    el("button", { class: "btn", onclick: closeModal }, "完成")
  ]);
  _chatMessages.push({ role: "assistant", content: "你好！我来帮你快速设置求职偏好。先问一下，你想在哪些城市工作？" });
}

async function sendChatMessage() {
  var input = document.getElementById("chat-input");
  var text = input.value.trim();
  if (!text) return;

  var msgBox = document.getElementById("chat-messages");
  msgBox.appendChild(el("div", { class: "chat-bubble user" },
    el("div", { class: "chat-text" }, text)
  ));
  input.value = "";
  msgBox.scrollTop = msgBox.scrollHeight;

  _chatMessages.push({ role: "user", content: text });

  // 显示AI思考中
  var loading = el("div", { class: "chat-bubble ai", id: "chat-loading" },
    el("div", { class: "chat-text" }, "思考中...")
  );
  msgBox.appendChild(loading);
  msgBox.scrollTop = msgBox.scrollHeight;

  try {
    // 获取简历文本
    var resumeText = "";
    try {
      var resumes = await API.get("/api/resume/list");
      var def = resumes.find(function(r) { return r.is_default && r.has_text; });
      if (def) {
        var rdata = await API.get("/api/resume/" + def.id + "/text");
        resumeText = rdata.raw_text || "";
      }
    } catch(e) {}

    var r = await API.post("/api/resume/preference/chat", {
      messages: _chatMessages,
      resume_text: resumeText
    });

    // 移除loading
    var lm = document.getElementById("chat-loading");
    if (lm) lm.remove();

    // 显示AI回复
    msgBox.appendChild(el("div", { class: "chat-bubble ai" },
      el("div", { class: "chat-text" }, r.reply || "好的，了解了")
    ));
    msgBox.scrollTop = msgBox.scrollHeight;
    _chatMessages.push({ role: "assistant", content: r.reply || "好的" });

    // 如果完成了，刷新偏好
    if (r.is_complete) {
      toast("✅ 偏好已自动保存！");
      loadPreference();
      setTimeout(function() { closeModal(); }, 2000);
    }
  } catch(e) {
    var lm2 = document.getElementById("chat-loading");
    if (lm2) lm2.remove();
    toast("AI服务暂不可用: " + e.message);
  }
}

// === 大模型设置 ===
async function loadLLMStatus() {
  var box = document.getElementById("llm-status");
  try {
    var h = await API.get("/api/health");
    box.innerHTML = "";
    box.appendChild(el("div", { class: "flex gap-8 center" },
      el("span", {}, "当前模型: "),
      el("span", { class: "tag primary" }, h.llm_provider),
      h.llm_configured
        ? el("span", { class: "tag ok" }, "已配置")
        : el("span", { class: "tag danger" }, "未配置")
    ));
    if (!h.llm_configured) {
      box.appendChild(el("div", { class: "text-sm muted mt-12" },
        "请在 backend/config.yaml 的 llm." + h.llm_provider + ".api_key 中填入 API Key"
      ));
    }
  } catch(e) { box.innerHTML = "加载失败"; }
}

// === 推送与日历 ===
async function testNotify() {
  var box = document.getElementById("notify-result");
  box.innerHTML = '<div class="loading">发送中…</div>';
  try {
    var r = await API.post("/api/notify/test");
    box.innerHTML = r.ok ? '<span class="tag ok">通知已发送</span>' : '<span class="tag danger">失败</span>';
  } catch(e) { box.innerHTML = '<span class="tag danger">失败</span>'; }
}

async function dailyPush() {
  var box = document.getElementById("notify-result");
  box.innerHTML = '<div class="loading">推送中…</div>';
  try {
    var r = await API.post("/api/notify/daily");
    box.innerHTML = r.ok ? '<span class="tag ok">已推送</span>' : '<span class="tag danger">失败</span>';
  } catch(e) { box.innerHTML = '<span class="tag danger">失败</span>'; }
}

async function syncCalendar() {
  var box = document.getElementById("notify-result");
  box.innerHTML = '<div class="loading">同步中…</div>';
  try {
    var r = await API.post("/api/notify/sync-calendar");
    box.innerHTML = '<span class="tag ok">同步完成</span>';
  } catch(e) { box.innerHTML = '<span class="tag danger">失败: ' + e.message + '</span>'; }
}
