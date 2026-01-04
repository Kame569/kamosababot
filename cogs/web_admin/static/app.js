(function () {
  "use strict";

  // ---------- helpers ----------
  function $(id) { return document.getElementById(id); }
  function q(sel) { return document.querySelector(sel); }
  function qa(sel) { return Array.from(document.querySelectorAll(sel)); }

  function toast(msg) {
    try {
      let box = $("__toast__");
      if (!box) {
        box = document.createElement("div");
        box.id = "__toast__";
        box.style.position = "fixed";
        box.style.right = "18px";
        box.style.bottom = "18px";
        box.style.zIndex = "9999";
        box.style.display = "flex";
        box.style.flexDirection = "column";
        box.style.gap = "10px";
        document.body.appendChild(box);
      }
      const t = document.createElement("div");
      t.textContent = msg;
      t.style.padding = "12px 14px";
      t.style.borderRadius = "12px";
      t.style.background = "rgba(0,0,0,0.75)";
      t.style.color = "#fff";
      t.style.border = "1px solid rgba(255,255,255,0.12)";
      t.style.backdropFilter = "blur(10px)";
      t.style.maxWidth = "420px";
      t.style.fontSize = "14px";
      box.appendChild(t);
      setTimeout(() => { try { t.remove(); } catch (_) {} }, 2600);
    } catch (_) {
      try { alert(msg); } catch (_) {}
    }
  }

  function setLoading(btn, on, text) {
    try {
      if (!btn) return;
      btn.disabled = !!on;
      btn.dataset._origText = btn.dataset._origText || btn.textContent;
      btn.textContent = on ? (text || "処理中…") : (btn.dataset._origText || btn.textContent);
      btn.style.opacity = on ? "0.75" : "1";
    } catch (_) {}
  }

  async function postJson(url, obj) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(obj || {})
    });
    const txt = await res.text();
    let json;
    try { json = txt ? JSON.parse(txt) : {}; } catch (_) { json = { raw: txt }; }
    if (!res.ok) {
      const err = (json && (json.error || json.message)) ? (json.error || json.message) : (res.status + " " + res.statusText);
      throw new Error(err);
    }
    return json;
  }

  function parseCsv(s) {
    return String(s || "")
      .split(",")
      .map(x => x.trim())
      .filter(x => x.length > 0);
  }

  // ---------- cfg ----------
  function loadCfg() {
    try {
      const n = $("cfg-json");
      if (!n) return {};
      return JSON.parse(n.textContent || "{}");
    } catch (e) {
      console.error("cfg-json parse error", e);
      return {};
    }
  }

  window.__CFG__ = loadCfg();

  // ---------- ticket data model ----------
  function ensureTicketPanel(panel) {
    panel = panel || {};
    if (typeof panel.panel_name !== "string") panel.panel_name = "panel";
    if (typeof panel.enabled !== "boolean") panel.enabled = true;

    panel.deploy = panel.deploy || { channel_id: "", message_id: "" };
    panel.permissions = panel.permissions || { staff_role_ids: [], viewer_role_ids: [] };
    panel.limits = panel.limits || { max_open_per_user: 5, cooldown_minutes: 30 };

    if (!panel.mode) panel.mode = "channel";
    if (!panel.name_template) panel.name_template = "ticket-{count}-{user}";
    if (!panel.parent_category_id) panel.parent_category_id = "";
    if (!panel.thread_parent_channel_id) panel.thread_parent_channel_id = "";

    panel.form = panel.form || {};
    if (typeof panel.form.enabled !== "boolean") panel.form.enabled = false;
    if (!Array.isArray(panel.form.fields)) panel.form.fields = [];

    panel.rules = panel.rules || {};
    if (typeof panel.rules.enabled !== "boolean") panel.rules.enabled = false;
    if (!panel.rules.title) panel.rules.title = "📌ルール・注意事項";
    if (typeof panel.rules.body !== "string") panel.rules.body = "";
    if (typeof panel.rules.allow_everyone_mention !== "boolean") panel.rules.allow_everyone_mention = false;
    if (!Array.isArray(panel.rules.allowed_role_ids)) panel.rules.allowed_role_ids = [];
    if (!panel.rules.policy) panel.rules.policy = "staff_only";

    panel.close = panel.close || {};
    if (typeof panel.close.confirm_required !== "boolean") panel.close.confirm_required = true;
    if (!panel.close.closed_category_id) panel.close.closed_category_id = "";
    if (typeof panel.close.allow_reopen !== "boolean") panel.close.allow_reopen = true;
    if (!panel.close.delete_after_days) panel.close.delete_after_days = 14;

    return panel;
  }

  function getPanels() {
    const cfg = window.__CFG__ || {};
    cfg.ticket = cfg.ticket || {};
    cfg.ticket.panels = cfg.ticket.panels || [];
    cfg.ticket.panels = cfg.ticket.panels.map(ensureTicketPanel);
    return cfg.ticket.panels;
  }

  function currentPanelIndex() {
    const sel = $("ticket_panel_select");
    if (!sel) return 0;
    const n = parseInt(sel.value || "0", 10);
    return Number.isFinite(n) ? n : 0;
  }

  function currentTab() {
    const form = $("tab_form");
    const rules = $("tab_rules");
    if (rules && rules.classList.contains("active")) return "rules";
    if (form && form.classList.contains("active")) return "form";
    return "form";
  }

  // ---------- UI: tabs ----------
  window.ticketChangeTab = function (tab) {
    tab = (tab === "rules") ? "rules" : "form";
    const btns = qa(".tabbtn");
    btns.forEach(b => {
      const isRules = b.textContent.includes("ルール");
      const active = (tab === "rules") ? isRules : !isRules;
      b.classList.toggle("active", active);
    });
    const pf = $("tab_form");
    const pr = $("tab_rules");
    if (pf) pf.classList.toggle("active", tab === "form");
    if (pr) pr.classList.toggle("active", tab === "rules");
  };

  // ---------- UI: forum ON/OFF (buttons) ----------
  function applyForumSeg(enabled) {
    const bOn = $("forum_btn_on");
    const bOff = $("forum_btn_off");
    if (bOn) bOn.classList.toggle("active", !!enabled);
    if (bOff) bOff.classList.toggle("active", !enabled);

    const chk = $("ticket_forum_enabled");
    if (chk) chk.checked = !!enabled;

    const body = $("forum_body");
    if (body) body.classList.toggle("off", !enabled);
  }

  window.ticketSetForum = function (enabled) {
    applyForumSeg(!!enabled);
  };

  // ---------- UI: form fields repeater ----------
  function fieldRowTemplate(field) {
    const f = field || { label: "項目名", type: "paragraph", required: true, hint: "" };
    const req = f.required ? "checked" : "";
    return `
      <div class="repeat-row">
        <div class="repeat-head">
          <div class="repeat-title">項目</div>
          <button class="btn mini danger" type="button" data-act="del-field">削除</button>
        </div>
        <div class="form-grid">
          <div class="field">
            <label>ラベル</label>
            <input class="input" data-k="label" value="${escapeHtml(f.label || "項目名")}">
          </div>
          <div class="field">
            <label>種類</label>
            <div class="select-wrap">
              <select class="select" data-k="type">
                <option value="text" ${f.type === "text" ? "selected" : ""}>短文</option>
                <option value="paragraph" ${(!f.type || f.type === "paragraph") ? "selected" : ""}>長文</option>
                <option value="url" ${f.type === "url" ? "selected" : ""}>URL</option>
              </select>
              <span class="chev">▾</span>
            </div>
          </div>
          <div class="field">
            <label>必須</label>
            <label class="switch">
              <input type="checkbox" data-k="required" ${req}>
              <span class="slider"></span>
            </label>
          </div>
          <div class="field">
            <label>説明（任意）</label>
            <input class="input" data-k="hint" value="${escapeHtml(f.hint || "")}">
          </div>
        </div>
      </div>
    `;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function renderFormFields(panel) {
    const wrap = $("ticket_form_fields");
    if (!wrap) return;
    wrap.innerHTML = "";
    const fields = (panel.form && Array.isArray(panel.form.fields)) ? panel.form.fields : [];
    fields.forEach(f => {
      const div = document.createElement("div");
      div.innerHTML = fieldRowTemplate(f);
      const row = div.firstElementChild;
      wrap.appendChild(row);
    });

    // bind delete buttons
    wrap.querySelectorAll('[data-act="del-field"]').forEach(btn => {
      btn.onclick = () => {
        const row = btn.closest(".repeat-row");
        if (row) row.remove();
      };
    });
  }

  window.ticketAddFormField = function () {
    const wrap = $("ticket_form_fields");
    if (!wrap) return;

    const div = document.createElement("div");
    div.innerHTML = fieldRowTemplate({ label: "項目名", type: "paragraph", required: true, hint: "" });
    const row = div.firstElementChild;
    wrap.appendChild(row);

    const del = row.querySelector('[data-act="del-field"]');
    if (del) del.onclick = () => row.remove();

    toast("＋ 項目を追加しました");
  };

  function collectFormFields() {
    const wrap = $("ticket_form_fields");
    if (!wrap) return [];
    const rows = qa("#ticket_form_fields .repeat-row");
    return rows.map(row => {
      const label = row.querySelector('[data-k="label"]')?.value || "項目名";
      const type = row.querySelector('[data-k="type"]')?.value || "paragraph";
      const required = !!row.querySelector('[data-k="required"]')?.checked;
      const hint = row.querySelector('[data-k="hint"]')?.value || "";
      return { label, type, required, hint };
    });
  }

  // ---------- Auto refresh on panel select ----------
  function renderPanelToUI(idx) {
    const panels = getPanels();
    const panel = ensureTicketPanel(panels[idx] || panels[0] || ensureTicketPanel({}));
    panels[idx] = panel;

    // basic
    if ($("ticket_panel_enabled")) $("ticket_panel_enabled").checked = !!panel.enabled;

    // forum
    applyForumSeg(!!(panel.form && panel.form.enabled));
    if ($("ticket_mode")) $("ticket_mode").value = panel.mode || "channel";
    if ($("ticket_name_template")) $("ticket_name_template").value = panel.name_template || "";
    if ($("ticket_parent_category")) $("ticket_parent_category").value = String(panel.parent_category_id || "");
    if ($("ticket_thread_parent")) $("ticket_thread_parent").value = String(panel.thread_parent_channel_id || "");
    if ($("ticket_staff_roles")) $("ticket_staff_roles").value = (panel.permissions.staff_role_ids || []).join(",");
    if ($("ticket_limit_max")) $("ticket_limit_max").value = String(panel.limits.max_open_per_user ?? 5);
    if ($("ticket_limit_cd")) $("ticket_limit_cd").value = String(panel.limits.cooldown_minutes ?? 30);
    if ($("ticket_deploy_channel")) $("ticket_deploy_channel").value = String(panel.deploy.channel_id || "");

    renderFormFields(panel);

    // rules
    if ($("ticket_rules_enabled")) $("ticket_rules_enabled").checked = !!panel.rules.enabled;
    if ($("ticket_rules_title")) $("ticket_rules_title").value = panel.rules.title || "📌ルール・注意事項";
    if ($("ticket_rules_body")) $("ticket_rules_body").value = panel.rules.body || "";
    if ($("ticket_rules_allow_everyone")) $("ticket_rules_allow_everyone").checked = !!panel.rules.allow_everyone_mention;
    if ($("ticket_rules_policy")) $("ticket_rules_policy").value = panel.rules.policy || "staff_only";
    if ($("ticket_rules_allowed_roles")) $("ticket_rules_allowed_roles").value = (panel.rules.allowed_role_ids || []).join(",");

    // keep cfg updated
    window.__CFG__.ticket.panels = panels;
  }

  // bind select change -> instant re-render
  function bindPanelSelectAutoRefresh() {
    const sel = $("ticket_panel_select");
    if (!sel) return;
    sel.addEventListener("change", () => {
      const idx = currentPanelIndex();
      renderPanelToUI(idx);
      toast("パネル表示を更新しました（保存はまだです）");
    });
  }

  // ---------- Save / Deploy / Panel CRUD ----------
  window.ticketSave = async function (gid) {
    const btn = $("ticket_save_btn");
    try {
      setLoading(btn, true, "保存中…");

      const cfg = window.__CFG__ || {};
      cfg.ticket = cfg.ticket || {};
      cfg.ticket.panels = getPanels();

      const idx = currentPanelIndex();
      const panel = ensureTicketPanel(cfg.ticket.panels[idx] || {});

      // basic
      panel.enabled = !!$("ticket_panel_enabled")?.checked;

      // forum
      panel.form.enabled = !!$("ticket_forum_enabled")?.checked;
      panel.mode = $("ticket_mode")?.value || "channel";
      panel.name_template = $("ticket_name_template")?.value || "ticket-{count}-{user}";
      panel.parent_category_id = $("ticket_parent_category")?.value || "";
      panel.thread_parent_channel_id = $("ticket_thread_parent")?.value || "";
      panel.permissions.staff_role_ids = parseCsv($("ticket_staff_roles")?.value || "")
        .filter(x => /^\d+$/.test(x))
        .map(x => parseInt(x, 10));
      panel.limits.max_open_per_user = parseInt($("ticket_limit_max")?.value || "5", 10);
      panel.limits.cooldown_minutes = parseInt($("ticket_limit_cd")?.value || "30", 10);
      panel.deploy.channel_id = $("ticket_deploy_channel")?.value || "";

      panel.form.fields = collectFormFields();

      // rules
      panel.rules.enabled = !!$("ticket_rules_enabled")?.checked;
      panel.rules.title = $("ticket_rules_title")?.value || "📌ルール・注意事項";
      panel.rules.body = $("ticket_rules_body")?.value || "";
      if (!panel.rules.body.trim()) {
        panel.rules.body =
`・個人情報は書かないでください
・誹謗中傷は禁止です
・緊急時はスタッフに連絡してください
・@everyone は原則禁止です`;
      }
      panel.rules.allow_everyone_mention = !!$("ticket_rules_allow_everyone")?.checked;
      panel.rules.policy = $("ticket_rules_policy")?.value || "staff_only";
      panel.rules.allowed_role_ids = parseCsv($("ticket_rules_allowed_roles")?.value || "")
        .filter(x => /^\d+$/.test(x))
        .map(x => parseInt(x, 10));

      cfg.ticket.panels[idx] = panel;

      await postJson(`/guild/${gid}/api/save_config`, cfg);

      // reload cfg in memory (keep in sync)
      window.__CFG__ = cfg;

      toast("✅ Ticket を保存しました");
    } catch (e) {
      console.error(e);
      alert("Ticket 保存に失敗: " + e.message);
    } finally {
      setLoading(btn, false, "保存");
    }
  };

  window.ticketDeploy = async function (gid) {
    const btn = $("ticket_deploy_btn");
    try {
      setLoading(btn, true, "設置中…");
      await window.ticketSave(gid);

      const idx = currentPanelIndex();
      const panels = getPanels();
      const panel = ensureTicketPanel(panels[idx]);

      const ch = String(panel.deploy.channel_id || "").trim();
      if (!/^\d+$/.test(ch)) throw new Error("設置先チャンネルが未指定です");

      const res = await postJson(`/guild/${gid}/api/ticket/panel/deploy`, {
        panel_index: idx,
        channel_id: ch
      });

      // message_id store
      panel.deploy.message_id = String(res.message_id || panel.deploy.message_id || "");
      panels[idx] = panel;
      window.__CFG__.ticket.panels = panels;

      toast("📌 TicketパネルをDiscordに設置/更新しました");
    } catch (e) {
      console.error(e);
      alert("設置に失敗: " + e.message);
    } finally {
      setLoading(btn, false, "Discordに設置");
    }
  };

  window.ticketAddPanel = async function (gid) {
    const btn = q(".head-actions .btn");
    try {
      setLoading(btn, true, "追加中…");
      const res = await postJson(`/guild/${gid}/api/ticket/panel/create`, { panel_name: "new" });
      const idx = parseInt(res.index ?? 0, 10);

      // after create, reload page to get roles/channels lists etc consistent
      const url = new URL(window.location.href);
      url.searchParams.set("panel", String(idx));
      url.searchParams.set("tab", currentTab());
      window.location.href = url.toString();
    } catch (e) {
      console.error(e);
      alert("パネル追加に失敗: " + e.message);
    } finally {
      setLoading(btn, false, "＋ パネル追加");
    }
  };

  window.ticketDeletePanel = async function (gid) {
    const btn = $("ticket_delete_btn");
    const idx = currentPanelIndex();
    if (!confirm("このパネルを削除します。設置済みメッセージも削除します。よろしいですか？")) return;

    try {
      setLoading(btn, true, "削除中…");
      await postJson(`/guild/${gid}/api/ticket/panel/delete`, { panel_index: idx });

      // reload to panel 0
      const url = new URL(window.location.href);
      url.searchParams.set("panel", "0");
      url.searchParams.set("tab", currentTab());
      window.location.href = url.toString();
    } catch (e) {
      console.error(e);
      alert("削除に失敗: " + e.message);
    } finally {
      setLoading(btn, false, "このパネルを削除");
    }
  };

  // ---------- init ----------
  document.addEventListener("DOMContentLoaded", () => {
    try {
      // cfg normalize
      const cfg = window.__CFG__ || {};
      cfg.ticket = cfg.ticket || {};
      cfg.ticket.panels = (cfg.ticket.panels || []).map(ensureTicketPanel);
      window.__CFG__ = cfg;

      bindPanelSelectAutoRefresh();

      // render current panel into UI immediately
      renderPanelToUI(currentPanelIndex());

      // init current tab active (server already set, but keep safe)
      window.ticketChangeTab(currentTab());

      // ensure forum seg is correct
      applyForumSeg(!!($("ticket_forum_enabled")?.checked));
    } catch (e) {
      console.error("init error", e);
    }
  });

})();
