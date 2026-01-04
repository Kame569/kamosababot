import logging
import json
import datetime
from pathlib import Path

import discord
from discord.ext import commands

from aiohttp import web
import aiohttp_jinja2
import jinja2

logger = logging.getLogger("WebManager")


# -------------------------
# helpers
# -------------------------
def deep_merge(dst, src):
    """dst に src を再帰マージ（dst優先で不足を埋める）"""
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return dst
    for k, v in src.items():
        if k not in dst:
            dst[k] = v
        else:
            if isinstance(dst[k], dict) and isinstance(v, dict):
                deep_merge(dst[k], v)
    return dst


def default_config():
    return {
        "lang": "ja",
        "jl": {
            "enabled": False,
            "channels": {"join": "", "leave": ""},
            "filters": {"ignore_bots": True},
            "join_embed": {
                "title": "Welcome!",
                "description": "{user} が参加しました",
                "color": "#5865F2",
                "footer": ""
            },
            "leave_embed": {
                "title": "Bye!",
                "description": "{user} が退出しました",
                "color": "#ED4245",
                "footer": ""
            }
        },
        "ticket": {
            "enabled": True,
            "panels": []
        },
        "rank": {
            "enabled": True,
            "embed": {
                "title": "ランク - {username}",
                "description": "レベル\n{level}\nXP\n{xp}/{next}\nメッセージ\n{messages}",
                "color": "#6D7CFF",
                "fields": [],
                "footer": {"text": "Ranking"}
            },
            "leaderboard": {
                "enabled": False,
                "channel_id": "",
                "message_id": "",
                "interval_minutes": 10,
                # ✅ 追加要件
                "mention": False,
                "show": {"text": True, "vc": True, "overall": True}
            }
        }
    }


def default_ticket_panel():
    return {
        "panel_name": "default",
        "enabled": True,
        "deploy": {"channel_id": "", "message_id": ""},

        "mode": "channel",  # channel / thread
        "parent_category_id": "",
        "thread_parent_channel_id": "",
        "name_template": "ticket-{count}-{user}",
        "types": ["質問", "不具合", "申請", "通報"],

        "limits": {"max_open_per_user": 5, "cooldown_minutes": 30},

        "permissions": {"staff_role_ids": [], "viewer_role_ids": []},

        "form": {"enabled": False, "fields": []},

        "rules": {
            "enabled": False,
            "title": "📌ルール・注意事項",
            "body": "",
            "allow_everyone_mention": False,
            "allowed_role_ids": [],
            "policy": "staff_only"
        },

        "close": {
            "confirm_required": True,
            "closed_category_id": "",
            "allow_reopen": True,
            "delete_after_days": 14
        },

        "auto_delete": {"enabled": False, "inactive_minutes": 0}
    }


def _safe_int(val, default=0):
    try:
        return int(val)
    except Exception:
        return default


def _iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# -------------------------
# WebManager
# -------------------------
class WebManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.root = Path(__file__).parent.resolve()

        # ✅ request をテンプレに必ず注入（request is undefined 再発防止）
        async def _inject_globals(request):
            return {"request": request}

        aiohttp_jinja2.setup(
            self.app,
            loader=jinja2.FileSystemLoader(str(self.root / "templates")),
            context_processors=[
                aiohttp_jinja2.request_processor,
                _inject_globals,
            ],
        )

        self.setup_routes()
        self._runner = None
        self._site = None

    def cog_unload(self):
        try:
            if self._runner:
                self.bot.loop.create_task(self._runner.cleanup())
        except Exception:
            pass

    def setup_routes(self):
        r = self.app.router

        # pages
        r.add_get("/", self.handle_home)
        r.add_get("/guild/{gid}", self.handle_guild_dashboard)

        r.add_get("/guild/{gid}/settings/jl", self.handle_jl_settings)
        r.add_get("/guild/{gid}/settings/ticket", self.handle_ticket_settings)
        r.add_get("/guild/{gid}/settings/rank", self.handle_rank_settings)

        # ticket logs pages
        r.add_get("/guild/{gid}/tickets", self.handle_ticket_logs)
        r.add_get("/guild/{gid}/tickets/{tid}", self.handle_ticket_view)
        r.add_get("/guild/{gid}/tickets/{tid}/download", self.handle_ticket_download)

        # apis
        r.add_post("/guild/{gid}/api/save_config", self.api_save_config)

        r.add_post("/guild/{gid}/api/ticket/panel/create", self.api_ticket_create_panel)
        r.add_post("/guild/{gid}/api/ticket/panel/update", self.api_ticket_update_panel)
        r.add_post("/guild/{gid}/api/ticket/panel/delete", self.api_ticket_delete_panel)
        r.add_post("/guild/{gid}/api/ticket/panel/deploy", self.api_ticket_deploy_panel)

        r.add_post("/guild/{gid}/api/rank/deploy", self.api_rank_deploy)

        # static
        r.add_static("/static/", path=str(self.root / "static"), name="static")

    async def start_web_server(self):
        if self._runner is not None:
            return
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", 8080)
        await self._site.start()
        logger.info("[WEB] Running on http://0.0.0.0:8080")

    # -------------------------
    # config storage
    # -------------------------
    def cfg_path(self, gid):
        return Path("settings/guilds/{}/config.json".format(gid))

    def get_guild_cfg(self, gid):
        p = self.cfg_path(gid)
        base = default_config()

        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            cfg = base
            if not cfg["ticket"]["panels"]:
                cfg["ticket"]["panels"] = [default_ticket_panel()]
            p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            return cfg

        try:
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}

        deep_merge(data, base)

        # ticket panels ensure
        if not data.get("ticket", {}).get("panels"):
            data["ticket"]["panels"] = [default_ticket_panel()]
        else:
            bp = default_ticket_panel()
            for i in range(len(data["ticket"]["panels"])):
                if not isinstance(data["ticket"]["panels"][i], dict):
                    data["ticket"]["panels"][i] = {}
                deep_merge(data["ticket"]["panels"][i], bp)

        # rank leaderboard ensure
        data.setdefault("rank", {})
        data["rank"].setdefault("leaderboard", {})
        deep_merge(data["rank"]["leaderboard"], base["rank"]["leaderboard"])

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def save_guild_cfg(self, gid, cfg):
        p = self.cfg_path(gid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # -------------------------
    # ticket logs storage (read-only in web)
    # -------------------------
    def ticket_dir(self, gid):
        d = Path("data/tickets/{}".format(gid))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ticket_index_path(self, gid):
        return self.ticket_dir(gid) / "index.json"

    def load_ticket_index(self, gid):
        p = self.ticket_index_path(gid)
        if not p.exists():
            p.write_text("[]", encoding="utf-8")
        try:
            raw = p.read_text(encoding="utf-8").strip()
            data = json.loads(raw) if raw else []
            if not isinstance(data, list):
                return []
            return data
        except Exception:
            return []

    def load_ticket_detail(self, gid, tid):
        p = self.ticket_dir(gid) / "{}.json".format(tid)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
            if not isinstance(data, dict):
                return None
            return data
        except Exception:
            return None

    # -------------------------
    # pages
    # -------------------------
    async def handle_home(self, request):
        await self.bot.wait_until_ready()

        guilds = []
        for g in self.bot.guilds:
            icon = "https://cdn.discordapp.com/embed/avatars/0.png"
            if g.icon:
                try:
                    icon = str(g.icon.url)
                except Exception:
                    pass
            guilds.append({
                "id": str(g.id),
                "name": g.name,
                "icon": icon,
                "members": getattr(g, "member_count", 0)
            })

        return aiohttp_jinja2.render_template("home.html", request, {"guilds": guilds})

    async def handle_guild_dashboard(self, request):
        gid = request.match_info["gid"]
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)

        stats_path = Path("data/stats/{}.json".format(gid))
        raw = {}
        if stats_path.exists():
            try:
                raw = json.loads(stats_path.read_text(encoding="utf-8"))
            except Exception:
                raw = {}

        dates = [(datetime.date.today() - datetime.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        msg_counts = [int(raw.get(d, {}).get("messages", 0)) for d in dates]
        stats = {"dates": [d[5:] for d in dates], "messages": msg_counts}

        return aiohttp_jinja2.render_template("guild_home.html", request, {
            "guild": guild,
            "cfg": cfg,
            "stats": stats
        })

    async def handle_jl_settings(self, request):
        gid = request.match_info["gid"]
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)

        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels] if guild else []
        return aiohttp_jinja2.render_template("settings_join_leave.html", request, {
            "guild": guild,
            "cfg": cfg,
            "channels": channels
        })

    async def handle_ticket_settings(self, request):
        gid = request.match_info["gid"]
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)

        tab = (request.query.get("tab") or "form").strip().lower()
        if tab not in ("form", "rules"):
            tab = "form"

        panel_index = _safe_int(request.query.get("panel", "0"), 0)
        panels = cfg["ticket"]["panels"]
        if panel_index < 0 or panel_index >= len(panels):
            panel_index = 0

        panel = panels[panel_index]

        roles = [{"id": str(r.id), "name": r.name} for r in guild.roles] if guild else []
        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels] if guild else []
        categories = [{"id": str(c.id), "name": c.name} for c in guild.categories] if guild else []

        return aiohttp_jinja2.render_template("settings_ticket.html", request, {
            "guild": guild,
            "cfg": cfg,
            "panels": panels,
            "panel_index": panel_index,
            "panel": panel,
            "tab": tab,
            "roles": roles,
            "channels": channels,
            "categories": categories
        })

    async def handle_rank_settings(self, request):
        gid = request.match_info["gid"]
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)

        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels] if guild else []
        return aiohttp_jinja2.render_template("settings_ranking.html", request, {
            "guild": guild,
            "cfg": cfg,
            "channels": channels
        })

    async def handle_ticket_logs(self, request):
        gid = request.match_info["gid"]
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)

        items = self.load_ticket_index(gid)
        # 新しい順
        def _key(x):
            return str(x.get("created_at", ""))
        items = sorted(items, key=_key, reverse=True)

        return aiohttp_jinja2.render_template("ticket_logs.html", request, {
            "guild": guild,
            "cfg": cfg,
            "tickets": items
        })

    def _ticket_to_html(self, guild, ticket, detail):
        """
        detail想定:
        {
          "ticket_id": "...",
          "created_at": "...",
          "status": "open/pending/closed/locked",
          "title": "...",
          "messages": [
             {"ts":"...", "author_name":"...", "author_id":"...", "content":"...", "attachments":[{"url":"...","filename":"..."}]}
          ]
        }
        """
        gname = guild.name if guild else "Guild"
        title = (detail or {}).get("title") or (ticket or {}).get("title") or "Ticket"
        tid = (detail or {}).get("ticket_id") or (ticket or {}).get("ticket_id") or "unknown"
        status = (detail or {}).get("status") or (ticket or {}).get("status") or "unknown"
        created = (detail or {}).get("created_at") or (ticket or {}).get("created_at") or ""
        msgs = (detail or {}).get("messages") or []

        def esc(s):
            s = "" if s is None else str(s)
            return (s.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
                     .replace('"', "&quot;"))

        rows = []
        for m in msgs:
            ts = esc(m.get("ts", ""))
            an = esc(m.get("author_name", ""))
            content = esc(m.get("content", ""))
            atts = m.get("attachments") or []
            att_html = ""
            if atts:
                links = []
                for a in atts:
                    url = esc(a.get("url", ""))
                    fn = esc(a.get("filename", url))
                    if url:
                        links.append(f'<a href="{url}" target="_blank" rel="noopener">{fn}</a>')
                if links:
                    att_html = '<div class="att">📎 ' + " / ".join(links) + "</div>"
            rows.append(f"""
            <div class="msg">
              <div class="meta"><span class="author">{an}</span><span class="ts">{ts}</span></div>
              <pre class="body">{content}</pre>
              {att_html}
            </div>
            """)

        body = "\n".join(rows) if rows else '<div class="empty">（メッセージなし）</div>'

        html = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>[{gname}] Ticket {tid}</title>
<style>
  body{{margin:0;background:#0f1117;color:#e6e6e6;font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial}}
  .wrap{{max-width:980px;margin:0 auto;padding:24px}}
  .card{{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:18px}}
  .h{{display:flex;gap:14px;flex-wrap:wrap;align-items:center;justify-content:space-between}}
  .title{{font-size:18px;font-weight:800}}
  .tag{{font-size:12px;padding:6px 10px;border-radius:999px;background:rgba(88,101,242,.16);border:1px solid rgba(88,101,242,.35)}}
  .sub{{opacity:.8;font-size:12px;margin-top:6px}}
  .msg{{margin-top:14px;padding:12px;border-radius:14px;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.06)}}
  .meta{{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:8px}}
  .author{{font-weight:700}}
  .ts{{opacity:.7;font-size:12px}}
  pre.body{{margin:0;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;font-size:13px;line-height:1.55}}
  .att{{margin-top:10px;font-size:12px;opacity:.9}}
  a{{color:#8ea6ff}}
  .empty{{opacity:.8;padding:14px}}
</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="h">
        <div>
          <div class="title">{esc(title)}</div>
          <div class="sub">Ticket ID: {esc(tid)} / Created: {esc(created)}</div>
        </div>
        <div class="tag">status: {esc(status)}</div>
      </div>
      {body}
    </div>
  </div>
</body>
</html>"""
        return html

    async def handle_ticket_view(self, request):
        gid = request.match_info["gid"]
        tid = request.match_info["tid"]
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)

        index = self.load_ticket_index(gid)
        ticket = next((x for x in index if str(x.get("ticket_id", "")) == str(tid)), None)
        detail = self.load_ticket_detail(gid, tid)

        html = self._ticket_to_html(guild, ticket, detail)
        return aiohttp_jinja2.render_template("ticket_view.html", request, {
            "guild": guild,
            "cfg": cfg,
            "ticket_id": tid,
            "html": html
        })

    async def handle_ticket_download(self, request):
        gid = request.match_info["gid"]
        tid = request.match_info["tid"]
        guild = self.bot.get_guild(int(gid))

        index = self.load_ticket_index(gid)
        ticket = next((x for x in index if str(x.get("ticket_id", "")) == str(tid)), None)
        detail = self.load_ticket_detail(gid, tid)

        html = self._ticket_to_html(guild, ticket, detail)
        filename = "ticket_{}.html".format(tid)

        return web.Response(
            body=html.encode("utf-8"),
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "Content-Disposition": 'attachment; filename="{}"'.format(filename)
            }
        )

    # -------------------------
    # APIs
    # -------------------------
    async def api_save_config(self, request):
        gid = request.match_info["gid"]
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"status": "ng", "error": "invalid json"}, status=400)

        deep_merge(data, default_config())

        # ensure ticket panels exist
        if not data.get("ticket", {}).get("panels"):
            data["ticket"]["panels"] = [default_ticket_panel()]
        else:
            bp = default_ticket_panel()
            for i in range(len(data["ticket"]["panels"])):
                if not isinstance(data["ticket"]["panels"][i], dict):
                    data["ticket"]["panels"][i] = {}
                deep_merge(data["ticket"]["panels"][i], bp)

        # ensure rank leaderboard exists
        data.setdefault("rank", {})
        data["rank"].setdefault("leaderboard", {})
        deep_merge(data["rank"]["leaderboard"], default_config()["rank"]["leaderboard"])

        self.save_guild_cfg(gid, data)
        return web.json_response({"status": "ok"})

    async def api_ticket_create_panel(self, request):
        gid = request.match_info["gid"]
        cfg = self.get_guild_cfg(gid)
        try:
            data = await request.json()
        except Exception:
            data = {}

        name = (data.get("panel_name") or "new panel").strip()[:32]
        newp = json.loads(json.dumps(default_ticket_panel(), ensure_ascii=False))
        newp["panel_name"] = name

        cfg["ticket"]["panels"].append(newp)
        self.save_guild_cfg(gid, cfg)
        return web.json_response({"status": "ok", "index": len(cfg["ticket"]["panels"]) - 1})

    async def api_ticket_update_panel(self, request):
        gid = request.match_info["gid"]
        cfg = self.get_guild_cfg(gid)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"status": "ng", "error": "invalid json"}, status=400)

        idx = _safe_int(data.get("panel_index", 0), 0)
        if idx < 0 or idx >= len(cfg["ticket"]["panels"]):
            return web.json_response({"status": "ng", "error": "invalid index"}, status=400)

        panel = data.get("panel") or {}
        if not isinstance(panel, dict):
            return web.json_response({"status": "ng", "error": "panel must be object"}, status=400)

        deep_merge(panel, default_ticket_panel())
        cfg["ticket"]["panels"][idx] = panel

        self.save_guild_cfg(gid, cfg)
        return web.json_response({"status": "ok"})

    async def api_ticket_delete_panel(self, request):
        gid = request.match_info["gid"]
        cfg = self.get_guild_cfg(gid)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"status": "ng", "error": "invalid json"}, status=400)

        idx = _safe_int(data.get("panel_index", -1), -1)

        if idx <= 0:
            return web.json_response({"status": "ng", "error": "default panel cannot be deleted"}, status=400)
        if idx >= len(cfg["ticket"]["panels"]):
            return web.json_response({"status": "ng", "error": "invalid index"}, status=400)

        # deployed message delete best-effort
        dep = cfg["ticket"]["panels"][idx].get("deploy", {}) or {}
        ch_id = dep.get("channel_id", "")
        msg_id = dep.get("message_id", "")

        try:
            g = self.bot.get_guild(int(gid))
            if g and str(ch_id).isdigit() and str(msg_id).isdigit():
                ch = g.get_channel(int(ch_id))
                if ch:
                    m = await ch.fetch_message(int(msg_id))
                    await m.delete()
        except Exception:
            logger.exception("failed to delete deployed panel message")

        cfg["ticket"]["panels"].pop(idx)
        self.save_guild_cfg(gid, cfg)
        return web.json_response({"status": "ok"})

    async def api_ticket_deploy_panel(self, request):
        gid = request.match_info["gid"]
        cfg = self.get_guild_cfg(gid)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"status": "ng", "error": "invalid json"}, status=400)

        idx = _safe_int(data.get("panel_index", 0), 0)
        channel_id = str(data.get("channel_id", "")).strip()

        if idx < 0 or idx >= len(cfg["ticket"]["panels"]):
            return web.json_response({"status": "ng", "error": "invalid index"}, status=400)
        if not channel_id.isdigit():
            return web.json_response({"status": "ng", "error": "invalid channel_id"}, status=400)

        guild = self.bot.get_guild(int(gid))
        if not guild:
            return web.json_response({"status": "ng", "error": "guild not found"}, status=404)

        channel = guild.get_channel(int(channel_id))
        if not channel:
            return web.json_response({"status": "ng", "error": "channel not found"}, status=404)

        ticket_cog = self.bot.get_cog("TicketSystem")
        if not ticket_cog or not hasattr(ticket_cog, "deploy_panel"):
            return web.json_response({"status": "ng", "error": "TicketSystem cog missing deploy_panel()"}, status=500)

        msg = await ticket_cog.deploy_panel(channel, idx)

        cfg["ticket"]["panels"][idx].setdefault("deploy", {})
        cfg["ticket"]["panels"][idx]["deploy"]["channel_id"] = str(channel.id)
        cfg["ticket"]["panels"][idx]["deploy"]["message_id"] = str(msg.id)
        self.save_guild_cfg(gid, cfg)

        return web.json_response({"status": "ok", "message_id": str(msg.id)})

    async def api_rank_deploy(self, request):
        gid = request.match_info["gid"]
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"status": "ng", "error": "invalid json"}, status=400)

        channel_id = str(data.get("channel_id", "")).strip()
        if not channel_id.isdigit():
            return web.json_response({"status": "ng", "error": "invalid channel_id"}, status=400)

        guild = self.bot.get_guild(int(gid))
        if not guild:
            return web.json_response({"status": "ng", "error": "guild not found"}, status=404)

        channel = guild.get_channel(int(channel_id))
        if not channel:
            return web.json_response({"status": "ng", "error": "channel not found"}, status=404)

        # 既存Ranking Cogの関数名に合わせる（両対応）
        rank_cog = self.bot.get_cog("Ranking")
        if not rank_cog:
            return web.json_response({"status": "ng", "error": "Ranking cog not loaded"}, status=500)

        msg = None
        if hasattr(rank_cog, "deploy_or_update_leaderboard"):
            msg = await rank_cog.deploy_or_update_leaderboard(guild, force_send=True)
        elif hasattr(rank_cog, "deploy_leaderboard"):
            msg = await rank_cog.deploy_leaderboard(channel)
        else:
            return web.json_response({"status": "ng", "error": "Ranking cog has no deploy method"}, status=500)

        cfg = self.get_guild_cfg(gid)
        cfg.setdefault("rank", {})
        cfg["rank"].setdefault("leaderboard", {})
        cfg["rank"]["leaderboard"]["channel_id"] = str(channel.id)
        if msg:
            cfg["rank"]["leaderboard"]["message_id"] = str(msg.id)
        self.save_guild_cfg(gid, cfg)

        return web.json_response({"status": "ok", "message_id": str(msg.id) if msg else ""})


async def setup(bot):
    cog = WebManager(bot)
    await bot.add_cog(cog)
    bot.loop.create_task(cog.start_web_server())
