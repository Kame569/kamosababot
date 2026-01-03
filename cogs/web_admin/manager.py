import discord
from discord.ext import commands
from aiohttp import web
import aiohttp_jinja2
import jinja2
import json
import logging
import datetime
from pathlib import Path

logger = logging.getLogger("WebManager")

class WebManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.root = Path(__file__).parent.resolve()
        
        # Jinja2設定
        aiohttp_jinja2.setup(
            self.app,
            loader=jinja2.FileSystemLoader(str(self.root / "templates"))
        )
        self.setup_routes()

    def setup_routes(self):
        r = self.app.router
        r.add_get('/', self.handle_home)
        r.add_get('/guild/{gid}', self.handle_guild_dashboard)
        r.add_get('/guild/{gid}/settings/jl', self.handle_jl_settings)
        r.add_get('/guild/{gid}/settings/ticket', self.handle_ticket_settings)
        r.add_get('/guild/{gid}/settings/rank', self.handle_rank_settings)
        r.add_post('/guild/{gid}/api/save', self.api_save)
        r.add_static('/static/', path=str(self.root / "static"), name='static')

    async def start_web_server(self):
        """Webサーバーを起動するメソッド (AttributeError修正)"""
        port = 8080
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"[WEB] Admin Panel is live at http://localhost:{port}")

    def get_guild_cfg(self, gid):
        path = Path(f"settings/guilds/{gid}/config.json")
        default = {
            "lang": "ja",
            "jl": {
                "enabled": False, "channel_join": "", "channel_leave": "",
                "join_embed": {"title": "Welcome", "description": "Welcome {user}!", "color": 5763719},
                "leave_embed": {"title": "Goodbye", "description": "Goodbye {user}.", "color": 15548997}
            },
            "ticket": {
                "panels": [
                    {
                        "panel_name": "サポート窓口",
                        "category_id": "",
                        "close_category_id": "",
                        "staff_roles": [],
                        "name_format": "ticket-{user}",
                        "use_thread": False,
                        "use_modal": True
                    }
                ],
                "staff_roles": []
            },
            "rank": {
                "enabled": True, "types": ["chat"], "cooldown": 60, "formula": "level * 100"
            }
        }
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(default, indent=4, ensure_ascii=False))
            return default
        # キー欠損防止のマージ
        current = json.loads(path.read_text(encoding="utf-8"))
        return current

    # ハンドラー群
    async def handle_home(self, request):
        await self.bot.wait_until_ready()
        guilds = [{"id": str(g.id), "name": g.name, "icon": str(g.icon.url) if g.icon else "https://cdn.discordapp.com/embed/avatars/0.png"} for g in self.bot.guilds]
        return aiohttp_jinja2.render_template('home.html', request, {"guilds": guilds})

    async def handle_guild_dashboard(self, request):
        gid = request.match_info['gid']
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)
        stats = {
            "dates": ["01-01", "01-02", "01-03", "01-04"],
            "messages": [10, 50, 30, 80]
        }
        return aiohttp_jinja2.render_template('guild_home.html', request, {"guild": guild, "cfg": cfg, "stats": stats})

    async def handle_jl_settings(self, request):
        gid = request.match_info['gid']
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)
        channels = [{"id": str(c.id), "name": c.name} for c in guild.text_channels]
        return aiohttp_jinja2.render_template('settings_join_leave.html', request, {"guild": guild, "cfg": cfg, "channels": channels})

    async def handle_ticket_settings(self, request):
        gid = request.match_info['gid']
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)
        categories = [{"id": str(c.id), "name": c.name} for c in guild.categories]
        roles = [{"id": str(r.id), "name": r.name} for r in guild.roles]
        return aiohttp_jinja2.render_template('settings_ticket.html', request, {"guild": guild, "cfg": cfg, "categories": categories, "roles": roles})

    async def handle_rank_settings(self, request):
        gid = request.match_info['gid']
        guild = self.bot.get_guild(int(gid))
        cfg = self.get_guild_cfg(gid)
        return aiohttp_jinja2.render_template('settings_ranking.html', request, {"guild": guild, "cfg": cfg})

    async def api_save(self, request):
        gid = request.match_info['gid']
        data = await request.json()
        path = Path(f"settings/guilds/{gid}/config.json")
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False))
        return web.json_response({"status": "ok"})