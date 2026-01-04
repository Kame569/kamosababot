/* =========================================================
   Web Admin - app.js (safe, no-throw oriented)
   - JSON-in-script approach (cfg-json)
   - Common helpers: postJson, toast, setLoading, parseCsv
   - Pages: Join/Leave save, Ranking save+deploy, Ticket save+deploy+panel CRUD
   ========================================================= */

(function () {
  "use strict";

  // ---------- Safe DOM helpers ----------
  function $(id) { return document.getElementById(id); }
  function elText(id) { const e = $(id); return e ? (e.value ?? e.textContent ?? "") : ""; }
  function elBool(id) { const e = $(id); return e ? !!e.checked : false; }
  function elSetLoading(btn, on, text) {
    try {
      if (!btn) return;
      btn.disabled = !!on;
      btn.dataset._origText = btn.dataset._origText || btn.textContent;
      btn.textContent = on ? (text || "処理中…") : (btn.dataset._origText || btn.textContent);
      btn.style.opacity = on ? "0.75" : "1";
    } catch (_) {}
  }

  // ---------- Toast (simple, safe) ----------
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
      // fallback
      try { alert(msg); } catch (_) {}
    }
  }

  // ---------- JSON fetch helper ----------
  async function postJson(url, obj) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(obj || {})
    });
    const text = await res.text();
    let json;
    try { json = text ? JSON.parse(text) : {}; } catch (_) { json = { raw: text }; }
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

  // ---------- Load cfg from <script id="cfg-json" type="application/json"> ----------
  function loadCfg() {
    try {
      const node = $("cfg-json");
      if (!node) return null;
      const raw = node.textContent || "{}";
      return JSON.parse(raw);
    } catch (e) {
      console.error("cfg-json parse error:", e);
      return null;
    }
  }

  // Keep a global copy (safe)
  window.__CFG__ = loadCfg() || window.__CFG__ || {};

  // ---------- Join/Leave ----------
  window.jlSave = async function (gid) {
    const btn = document.querySelector("button[onclick^=\"jlSave\"]");
    try {
      elSetLoading(btn, true, "保存中…");
      const cfg = window.__CFG__ || {};
      cfg.jl = cfg.jl || {};
      cfg.jl.enabled = elBool("jl_enabled");

      cfg.jl.channels = cfg.jl.channels || {};
      cfg.jl.channels.join = elText("jl_channel_join").trim();
      cfg.jl.channels.leave = elText("jl_channel_leave").trim();

      await postJson(`/guild/${gid}/api/save_config`, cfg);
      toast("✅ Join/Leave を保存しました");
    } catch (e) {
      console.error(e);
      alert("Join/Leave 保存に失敗: " + e.message);
    } finally {
      elSetLoading(btn, false, "保存");
    }
  };

  // ---------- Ranking ----------
  window.rankSave = async function (gid) {
    const btn = document.querySelector("button[onclick^=\"rankSave\"]");
    try {
      elSetLoading(btn, true, "保存中…");

      const cfg = window.__CFG__ || {};
      cfg.rank = cfg.rank || {};
      cfg.rank.enabled = elBool("rank_enabled");

      cfg.rank.embed = cfg.rank.embed || {};
      if ($("rank_title")) cfg.rank.embed.title = elText("rank_title");
      if ($("rank_desc")) cfg.rank.embed.description = elText("rank_desc");
      if ($("rank_color")) cfg.rank.embed.color = elText("rank_color");

      cfg.rank.leaderboard = cfg.rank.leaderboard || {};
      if ($("lb_enabled")) cfg.rank.leaderboard.enabled = elBool("lb_enabled");
      if ($("lb_channel")) cfg.rank.leaderboard.channel_id = elText("lb_channel").trim();
      if ($("lb_interval")) cfg.rank.leaderboard.interval_minutes = parseInt(elText("lb_interval") || "10", 10);

      await postJson(`/guild/${gid}/api/save_config`, cfg);
      toast("✅ Ranking を保存しました");
    } catch (e) {
      console.error(e);
      alert("Ranking 保存に失敗: " + e.message);
    } finally {
      elSetLoading(btn, false, "保存");
    }
  };

  window.rankDeploy = async function (gid) {
    const btn = document.querySelector("button[onclick^=\"rankDeploy\"]");
    try {
      elSetLoading(btn, true, "設置中…");
      await window.rankSave(gid);

      const cfg = window.__CFG__ || {};
      const ch = (cfg.rank && cfg.rank.leaderboard) ? String(cfg.rank.leaderboard.channel_id || "").trim() : "";
      if (!/^\d+$/.test(ch)) throw new Error("設置先チャンネルが未指定です");

      await postJson(`/guild/${gid}/api/rank/deploy`, { channel_id: ch });
      toast("📌 Leaderboard をDiscordに設置/更新しました");
    } catch (e) {
      console.error(e);
      alert("設置に失敗: " + e.message);
    } finally {
      elSetLoading(btn, false, "Discordに設置");
    }
  };

  // ---------- Ticket helpers ----------
  function ensureTicketPanel(panel) {
    panel = panel || {};
    panel.deploy = panel.deploy || { channel_id: "", message_id: "" };
    panel.permissions = panel.permissions || { staff_role_ids: [], viewer_role_ids: [] };
    panel.limits = panel.limits || { max_open_per_user: 5, cooldown_minutes: 30 };
    panel.form = panel.form || {};
    if (typeof panel.form.enabled !== "boolean") panel.form.enabled = false;
    if (!Array.isArray(panel.form.fields)) panel.form.fields = [];
    panel.rules = panel.rules || {};
    if (typeof panel.rules.enabled !== "boolean") panel.rules.enabled = false;
    if (!Array.isArray(panel.rules.allowed_role_ids)) panel.rules.allowed_role_ids = [];
    if (!panel.rules.policy) panel.rules.policy = "staff_only";
    panel.close = panel.close || { confirm_required: true, closed_category_id: "", allow_reopen: true, delete_after_days: 14 };
    return panel;
  }

  function currentPanelIndex() {
    const sel = $("ticket_panel_select");
    if (!sel) return 0;
    const n = parseInt(sel.value || "0", 10);
    return Number.isFinite(n) ? n : 0;
  }

  window.ticketSwitchPanel = function (gid) {
    const idx = currentPanelIndex();
    const url = new URL(window.location.href);
    url.searchParams.set("panel", String(idx));
    if (!url.searchParams.get("tab")) url.searchParams.set("tab", "form");
    window.location.href = url.toString();
  };

  // Repeater UI
  window.ticketAddFormField = function () {
    const wrap = $("ticket_form_fields");
    if (!wrap) return;

    const row = document.createElement("div");
    row.className = "repeat-row";
    row.innerHTML = `
      <div class="repeat-head">
        <div class="repeat-title">項目</div>
        <button class="btn mini danger" type="button">削除</button>
      </div>
      <div class="form-grid">
        <div class="field">
          <label>ラベル</label>
          <input class="input" data-k="label" value="項目名">
        </div>
        <div class="field">
          <label>種類</label>
          <div class="select-wrap">
            <select class="select" data-k="type">
              <option value="text">短文</option>
              <option value="paragraph" selected>長文</option>
              <option value="url">URL</option>
            </select>
            <span class="chev">▾</span>
          </div>
        </div>
        <div class="field">
          <label>必須</label>
          <label class="switch">
            <input type="checkbox" data-k="required" checked>
            <span class="slider"></span>
          </label>
        </div>
        <div class="field">
          <label>説明（任意）</label>
          <input class="input" data-k="hint" value="">
        </div>
      </div>
    `;
    row.querySelector("button.danger").onclick = () => row.remove();
    wrap.appendChild(row);
  };

  function loadFormFields(panel) {
    const wrap = $("ticket_form_fields");
    if (!wrap) return;
    wrap.innerHTML = "";
    const fields = (panel.form && Array.isArray(panel.form.fields)) ? panel.form.fields : [];
    fields.forEach(f => {
      window.ticketAddFormField();
      const row = wrap.lastElementChild;
      row.querySelector('[data-k="label"]').value = f.label || "項目名";
      row.querySelector('[data-k="type"]').value = f.type || "paragraph";
      row.querySelector('[data-k="required"]').checked = !!f.required;
      row.querySelector('[data-k="hint"]').value = f.hint || "";
    });
  }

  function collectFormFields() {
    const wrap = $("ticket_form_fields");
    if (!wrap) return [];
    const rows = Array.from(wrap.querySelectorAll(".repeat-row"));
    return rows.map(row => {
      const label = row.querySelector('[data-k="label"]').value || "項目名";
      const type = row.querySelector('[data-k="type"]').value || "paragraph";
      const required = row.querySelector('[data-k="required"]').checked;
      const hint = row.querySelector('[data-k="hint"]').value || "";
      return { label, type, required, hint };
    });
  }

  // On load, hydrate ticket repeater if exists
  document.addEventListener("DOMContentLoaded", () => {
    try {
      const cfg = window.__CFG__ || {};
      if (!cfg.ticket || !Array.isArray(cfg.ticket.panels)) return;
      const idx = currentPanelIndex();
      cfg.ticket.panels[idx] = ensureTicketPanel(cfg.ticket.panels[idx]);
      loadFormFields(cfg.ticket.panels[idx]);
    } catch (e) {
      console.error("DOMContentLoaded hydrate error:", e);
    }
  });

  window.ticketSave = async function (gid) {
    const btn = $("ticket_save_btn");
    try {
      elSetLoading(btn, true, "保存中…");

      const cfg = window.__CFG__ || {};
      cfg.ticket = cfg.ticket || {};
      cfg.ticket.panels = cfg.ticket.panels || [];

      const idx = currentPanelIndex();
      const panel = ensureTicketPanel(cfg.ticket.panels[idx] || {});
      panel.enabled = elBool("ticket_panel_enabled");

      // form tab controls
      if ($("ticket_forum_enabled")) {
        panel.form.enabled = elBool("ticket_forum_enabled");
        if ($("ticket_mode")) panel.mode = elText("ticket_mode");
        if ($("ticket_name_template")) panel.name_template = elText("ticket_name_template");
        if ($("ticket_parent_category")) panel.parent_category_id = elText("ticket_parent_category");
        if ($("ticket_thread_parent")) panel.thread_parent_channel_id = elText("ticket_thread_parent");

        if ($("ticket_staff_roles")) {
          panel.permissions.staff_role_ids = parseCsv(elText("ticket_staff_roles"))
            .filter(x => /^\d+$/.test(x))
            .map(x => parseInt(x, 10));
        }
        if ($("ticket_limit_max")) panel.limits.max_open_per_user = parseInt(elText("ticket_limit_max") || "5", 10);
        if ($("ticket_limit_cd")) panel.limits.cooldown_minutes = parseInt(elText("ticket_limit_cd") || "30", 10);

        panel.form.fields = collectFormFields();
      }

      // rules tab controls
      if ($("ticket_rules_enabled")) {
        panel.rules.enabled = elBool("ticket_rules_enabled");
        panel.rules.title = (elText("ticket_rules_title") || "📌ルール・注意事項");
        panel.rules.body = (elText("ticket_rules_body") || "");

        if (!panel.rules.body.trim()) {
          panel.rules.body =
`・個人情報は書かないでください
・誹謗中傷は禁止です
・緊急時はスタッフに連絡してください
・@everyone は原則禁止です`;
        }

        panel.rules.allow_everyone_mention = elBool("ticket_rules_allow_everyone");
        panel.rules.allowed_role_ids = parseCsv(elText("ticket_rules_allowed_roles"))
          .filter(x => /^\d+$/.test(x))
          .map(x => parseInt(x, 10));
        panel.rules.policy = elText("ticket_rules_policy") || "staff_only";
      }

      cfg.ticket.panels[idx] = panel;

      await postJson(`/guild/${gid}/api/save_config`, cfg);
      toast("✅ Ticket を保存しました");
    } catch (e) {
      console.error(e);
      alert("Ticket 保存に失敗: " + e.message);
    } finally {
      elSetLoading(btn, false, "保存");
    }
  };

  window.ticketDeploy = async function (gid) {
    const btn = $("ticket_deploy_btn");
    try {
      elSetLoading(btn, true, "設置中…");
      await window.ticketSave(gid);

      const cfg = window.__CFG__ || {};
      const idx = currentPanelIndex();
      const panel = ensureTicketPanel((cfg.ticket && cfg.ticket.panels) ? cfg.ticket.panels[idx] : {});
      const ch = String(panel.deploy.channel_id || "").trim();

      if (!/^\d+$/.test(ch)) {
        throw new Error("設置先チャンネルIDが未指定です（panel.deploy.channel_id を設定UIに追加してください）");
      }

      await postJson(`/guild/${gid}/api/ticket/panel/deploy`, { panel_index: idx, channel_id: ch });
      toast("📌 TicketパネルをDiscordに設置/更新しました");
    } catch (e) {
      console.error(e);
      alert("設置に失敗: " + e.message);
    } finally {
      elSetLoading(btn, false, "Discordに設置");
    }
  };

  window.ticketAddPanel = async function (gid) {
    try {
      const j = await postJson(`/guild/${gid}/api/ticket/panel/create`, { panel_name: "new" });
      toast("✅ パネルを追加しました");
      const idx = j.index || 0;
      const url = new URL(window.location.href);
      url.searchParams.set("panel", String(idx));
      url.searchParams.set("tab", "form");
      window.location.href = url.toString();
    } catch (e) {
      console.error(e);
      alert("追加に失敗: " + e.message);
    }
  };

  window.ticketDeletePanel = async function (gid) {
    const idx = currentPanelIndex();
    if (!confirm("このパネルを削除します。設置済みメッセージがある場合も削除します。よろしいですか？")) return;
    try {
      await postJson(`/guild/${gid}/api/ticket/panel/delete`, { panel_index: idx });
      toast("🗑️ パネルを削除しました");
      const url = new URL(window.location.href);
      url.searchParams.set("panel", "0");
      url.searchParams.set("tab", "form");
      window.location.href = url.toString();
    } catch (e) {
      console.error(e);
      alert("削除に失敗: " + e.message);
    }
  };

})();
