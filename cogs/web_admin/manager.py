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
            "filters": {"ignore_bots": True},
            "channels": {"join": "", "leave": ""},
            "display": {
                "show_id": True,
                "show_created_at": True,
                "show_join_position": False,
                "show_member_count": True,
                "show_avatar": True
            },
            "join_embed": {
                "title": "Welcome!",
                "description": "{user} が参加しました",
                "color": "#5865F2",
                "footer": " "
            },
            "leave_embed": {
                "title": "Bye!",
                "description": "{user} が退出しました",
                "color": "#ED4245",
                "footer": " "
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
                "interval_minutes": 10
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

        "permissions": {
            "staff_role_ids": [],
            "viewer_role_ids": []
        },

        # ★今回の方針：フォーラム/ルールは独立ON/OFF、フォーム項目は無制限
        "form": {
            "enabled": False,
            "fields": []  # [{label,type(required text/paragraph/url), required(bool), hint(str)}]
        },

        "rules": {
            "enabled": False,
            "title": "📌ルール・注意事項",
            "body": "",
            "allow_everyone_mention": False,
            "allowed_role_ids": [],
            "policy": "staff_only"  # staff_only / allowed_roles / staff_or_allowed
        },

        "close": {
            "confirm_required": True,
            "closed_category_id": "",
            "allow_reopen": True,
            "delete_after_days": 14
        },

        "auto_delete": {
            "enabled": False,
            "inactive_minutes": 0
        }
    }


class WebManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.root = Path(__file__).parent.resolve()

        # ✅ 再発防止：request を必ず context に入れる（テンプレで request を使ってもUndefinedにならない）
        async def _inject_globals(request):
            return {"request": request}

        aiohttp_jinja2.setup(
            self.app,
            loader=jinja2.FileSystemLoader(str(self.root / "templates")),
            context_processors=[
                aiohttp_jinja2.request_processor,
                _inject_globals,  # ✅ async なので await できる
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

        r.add_get("/", self.handle_home)
        r.add_get("/guild/{gid}", self.handle_guild_dashboard)

        r.add_get("/guild/{gid}/settings/jl", self.handle_jl_settings)
        r.add_get("/guild/{gid}/settings/ticket", self.handle_ticket_settings)
        r.add_get("/guild/{gid}/settings/rank", self.handle_rank_settings)

        r.add_post("/guild/{gid}/api/save_config", self.api_save_config)

        r.add_post("/guild/{gid}/api/ticket/panel/create", self.api_ticket_create_panel)
        r.add_post("/guild/{gid}/api/ticket/panel/update", self.api_ticket_update_panel)
        r.add_post("/guild/{gid}/api/ticket/panel/delete", self.api_ticket_delete_panel)
        r.add_post("/guild/{gid}/api/ticket/panel/deploy", self.api_ticket_deploy_panel)

        r.add_post("/guild/{gid}/api/rank/deploy", self.api_rank_deploy)

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
    # config storage helpers
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

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def save_guild_cfg(self, gid, cfg):
        p = self.cfg_path(gid)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

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
        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]

        return aiohttp_jinja2.render_template("settings_join_leave.html", request, {
            "guild": guild,
            "cfg": cfg,
            "channels": channels
        })

    async def handle_ticket_settings(self, request):
        gid = request.match_info["gid"]
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)

        # ✅ request.query をテンプレで触らない：ここで安全に計算して渡す
        tab = (request.query.get("tab") or "form").strip().lower()
        if tab not in ("form", "rules"):
            tab = "form"

        try:
            panel_index = int(request.query.get("panel", "0"))
        except Exception:
            panel_index = 0

        panels = cfg["ticket"]["panels"]
        if panel_index < 0 or panel_index >= len(panels):
            panel_index = 0

        panel = panels[panel_index]

        roles = [{"id": str(r.id), "name": r.name} for r in guild.roles]
        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]
        categories = [{"id": str(c.id), "name": c.name} for c in guild.categories]

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
        roles = [{"id": str(r.id), "name": r.name} for r in guild.roles]
        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]

        return aiohttp_jinja2.render_template("settings_ranking.html", request, {
            "guild": guild,
            "cfg": cfg,
            "roles": roles,
            "channels": channels
        })

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
        if not data.get("ticket", {}).get("panels"):
            data["ticket"]["panels"] = [default_ticket_panel()]
        else:
            bp = default_ticket_panel()
            for i in range(len(data["ticket"]["panels"])):
                if not isinstance(data["ticket"]["panels"][i], dict):
                    data["ticket"]["panels"][i] = {}
                deep_merge(data["ticket"]["panels"][i], bp)

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

        try:
            idx = int(data.get("panel_index", 0))
        except Exception:
            idx = 0

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

        try:
            idx = int(data.get("panel_index", -1))
        except Exception:
            idx = -1

        if idx <= 0:
            return web.json_response({"status": "ng", "error": "default panel cannot be deleted"}, status=400)
        if idx >= len(cfg["ticket"]["panels"]):
            return web.json_response({"status": "ng", "error": "invalid index"}, status=400)

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

        try:
            idx = int(data.get("panel_index", 0))
        except Exception:
            idx = 0

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

        rank_cog = self.bot.get_cog("Ranking")
        if not rank_cog or not hasattr(rank_cog, "deploy_leaderboard"):
            return web.json_response({"status": "ng", "error": "Ranking cog missing deploy_leaderboard()"}, status=500)

        msg = await rank_cog.deploy_leaderboard(channel)

        cfg = self.get_guild_cfg(gid)
        cfg.setdefault("rank", {})
        cfg["rank"].setdefault("leaderboard", {})
        cfg["rank"]["leaderboard"]["channel_id"] = str(channel.id)
        if msg:
            cfg["rank"]["leaderboard"]["message_id"] = str(msg.id)
        self.save_guild_cfg(gid, cfg)

        return web.json_response({"status": "ok", "message_id": str(msg.id) if msg else ""})


async def setup(bot):
    # NOTE: Cogとしてロードされる前提
    cog = WebManager(bot)
    await bot.add_cog(cog)
    # Web起動（Bot側の setup_hook 後に呼ばれてもOK）
    bot.loop.create_task(cog.start_web_server())
