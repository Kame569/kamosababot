(function () {
  "use strict";

  // ---------- Safe DOM helpers ----------
  function $(id) { return document.getElementById(id); }
  function elText(id) { const e = $(id); return e ? (e.value ?? e.textContent ?? "") : ""; }
  function elBool(id) { const e = $(id); return e ? !!e.checked : false; }

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
      setTimeout(() => { try { t.remove(); } catch (_) {} }, 2200);
    } catch (_) {
      try { alert(msg); } catch (_) {}
    }
  }

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

  // ---------- Load cfg from <script id="cfg-json" type="application/json"> ----------
  function loadCfg() {
    try {
      const node = $("cfg-json");
      if (!node) return null;
      return JSON.parse(node.textContent || "{}");
    } catch (e) {
      console.error("cfg-json parse error:", e);
      return null;
    }
  }
  window.__CFG__ = loadCfg() || window.__CFG__ || {};

  // ---------- debounce auto-save ----------
  function debounce(fn, ms) {
    let t = null;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  function _parseHexColor(s, fallback) {
    s = String(s || "").trim();
    if (!s) return fallback;
    if (!s.startsWith("#")) s = "#" + s;
    if (/^#[0-9a-fA-F]{6}$/.test(s)) return s;
    return fallback;
  }

  // ---------- Join/Leave save + preview ----------
  function jlCollect(cfg) {
    cfg = cfg || {};
    cfg.jl = cfg.jl || {};
    cfg.jl.enabled = elBool("jl_enabled");
    cfg.jl.channels = cfg.jl.channels || {};
    cfg.jl.channels.join = elText("jl_channel_join").trim();
    cfg.jl.channels.leave = elText("jl_channel_leave").trim();

    cfg.jl.join_embed = cfg.jl.join_embed || {};
    cfg.jl.leave_embed = cfg.jl.leave_embed || {};

    cfg.jl.join_embed.title = elText("jl_join_title");
    cfg.jl.join_embed.description = elText("jl_join_desc");
    cfg.jl.join_embed.color = _parseHexColor(elText("jl_join_color"), "#5865F2");
    cfg.jl.join_embed.footer = elText("jl_join_footer");

    cfg.jl.leave_embed.title = elText("jl_leave_title");
    cfg.jl.leave_embed.description = elText("jl_leave_desc");
    cfg.jl.leave_embed.color = _parseHexColor(elText("jl_leave_color"), "#ED4245");
    cfg.jl.leave_embed.footer = elText("jl_leave_footer");

    return cfg;
  }

  function jlPreview() {
    try {
      const join = {
        title: elText("jl_join_title"),
        desc: elText("jl_join_desc"),
        color: _parseHexColor(elText("jl_join_color"), "#5865F2"),
        footer: elText("jl_join_footer")
      };
      const leave = {
        title: elText("jl_leave_title"),
        desc: elText("jl_leave_desc"),
        color: _parseHexColor(elText("jl_leave_color"), "#ED4245"),
        footer: elText("jl_leave_footer")
      };

      const jBox = $("jl_preview_join");
      const lBox = $("jl_preview_leave");

      function render(box, e) {
        if (!box) return;
        box.innerHTML = `
          <div class="pill">Embed preview</div>
          <div style="margin-top:10px;border-left:4px solid ${e.color};padding-left:12px">
            <div style="font-weight:900">${escapeHtml(e.title || "")}</div>
            <div style="opacity:.9; margin-top:6px; white-space:pre-wrap">${escapeHtml(e.desc || "")}</div>
            ${e.footer ? `<div style="opacity:.7;font-size:12px;margin-top:10px">${escapeHtml(e.footer)}</div>` : ``}
          </div>
        `;
      }

      render(jBox, join);
      render(lBox, leave);
    } catch (e) {
      console.error("jlPreview error:", e);
    }
  }

  function escapeHtml(s) {
    s = String(s ?? "");
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  window.jlSave = async function (gid, quiet) {
    try {
      const cfg = jlCollect(window.__CFG__ || {});
      await postJson(`/guild/${gid}/api/save_config`, cfg);
      window.__CFG__ = cfg;
      jlPreview();
      if (!quiet) toast("✅ Join/Leave を保存しました");
    } catch (e) {
      console.error(e);
      alert("Join/Leave 保存に失敗: " + e.message);
    }
  };

  const jlAutoSave = debounce((gid) => window.jlSave(gid, true), 450);

  // ---------- Ranking save + deploy ----------
  function rankCollect(cfg) {
    cfg = cfg || {};
    cfg.rank = cfg.rank || {};
    cfg.rank.enabled = elBool("rank_enabled");

    cfg.rank.embed = cfg.rank.embed || {};
    cfg.rank.embed.title = elText("rank_title");
    cfg.rank.embed.description = elText("rank_desc");
    cfg.rank.embed.color = _parseHexColor(elText("rank_color"), "#6D7CFF");

    cfg.rank.leaderboard = cfg.rank.leaderboard || {};
    cfg.rank.leaderboard.enabled = elBool("lb_enabled");
    cfg.rank.leaderboard.channel_id = elText("lb_channel").trim();
    cfg.rank.leaderboard.interval_minutes = parseInt(elText("lb_interval") || "10", 10);

    // ✅ 要件追加：メンション/表示対象
    cfg.rank.leaderboard.mention = elBool("lb_mention");
    cfg.rank.leaderboard.show = cfg.rank.leaderboard.show || {};
    cfg.rank.leaderboard.show.text = elBool("lb_show_text");
    cfg.rank.leaderboard.show.vc = elBool("lb_show_vc");
    cfg.rank.leaderboard.show.overall = elBool("lb_show_overall");

    return cfg;
  }

  window.rankSave = async function (gid, quiet) {
    try {
      const cfg = rankCollect(window.__CFG__ || {});
      await postJson(`/guild/${gid}/api/save_config`, cfg);
      window.__CFG__ = cfg;
      if (!quiet) toast("✅ Ranking を保存しました");
    } catch (e) {
      console.error(e);
      alert("Ranking 保存に失敗: " + e.message);
    }
  };

  const rankAutoSave = debounce((gid) => window.rankSave(gid, true), 450);

  window.rankDeploy = async function (gid) {
    try {
      await window.rankSave(gid, true);

      const cfg = window.__CFG__ || {};
      const ch = String(cfg.rank?.leaderboard?.channel_id || "").trim();
      if (!/^\d+$/.test(ch)) throw new Error("設置先チャンネルが未指定です");

      await postJson(`/guild/${gid}/api/rank/deploy`, { channel_id: ch });
      toast("📌 Leaderboard をDiscordに設置/更新しました");
    } catch (e) {
      console.error(e);
      alert("設置に失敗: " + e.message);
    }
  };

  // ---------- wire auto-save (if elements exist) ----------
  document.addEventListener("DOMContentLoaded", () => {
    try {
      const gidNode = $("gid");
      const gid = gidNode ? gidNode.value : null;

      // previews
      jlPreview();

      if (gid) {
        // Join/Leave: immediate save on change
        const jlIds = [
          "jl_enabled", "jl_channel_join", "jl_channel_leave",
          "jl_join_title", "jl_join_desc", "jl_join_color", "jl_join_footer",
          "jl_leave_title", "jl_leave_desc", "jl_leave_color", "jl_leave_footer"
        ];
        jlIds.forEach(id => {
          const el = $(id);
          if (el) {
            el.addEventListener("input", () => { jlPreview(); jlAutoSave(gid); });
            el.addEventListener("change", () => { jlPreview(); jlAutoSave(gid); });
          }
        });

        // Ranking: immediate save on change
        const rIds = [
          "rank_enabled","rank_title","rank_desc","rank_color",
          "lb_enabled","lb_channel","lb_interval","lb_mention",
          "lb_show_text","lb_show_vc","lb_show_overall"
        ];
        rIds.forEach(id => {
          const el = $(id);
          if (el) {
            el.addEventListener("input", () => rankAutoSave(gid));
            el.addEventListener("change", () => rankAutoSave(gid));
          }
        });
      }
    } catch (e) {
      console.error("DOMContentLoaded wiring error:", e);
    }
  });

})();
