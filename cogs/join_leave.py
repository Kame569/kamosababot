import logging
import datetime
import discord
from discord.ext import commands

from utils.storage import load_guild_config

logger = logging.getLogger("JoinLeave")


def _parse_color(val, default=discord.Color.blurple()):
    try:
        if isinstance(val, str):
            s = val.strip()
            if s.startswith("#"):
                s = s[1:]
            if len(s) == 6:
                return discord.Color(int(s, 16))
    except Exception:
        pass
    return default

def _render_vars(text, member, guild):
    now = datetime.datetime.utcnow()
    return (text or "").replace("{user}", member.mention)\
        .replace("{user_id}", str(member.id))\
        .replace("{created_at}", str(getattr(member, "created_at", "")))\
        .replace("{member_count}", str(getattr(guild, "member_count", 0)))

def _make_embed(embed_cfg, member, guild, fields_cfg):
    e = discord.Embed(
        title=_render_vars(embed_cfg.get("title", ""), member, guild),
        description=_render_vars(embed_cfg.get("description", ""), member, guild),
        color=_parse_color(embed_cfg.get("color", "#5865F2"), discord.Color.blurple())
    )
    # optional fields
    if fields_cfg.get("show_id", True):
        e.add_field(name="ID", value=str(member.id), inline=True)
    if fields_cfg.get("show_created_at", True):
        e.add_field(name="作成日", value=str(getattr(member, "created_at", "")), inline=True)
    if fields_cfg.get("show_member_count", True):
        e.add_field(name="メンバー数", value=str(getattr(guild, "member_count", 0)), inline=True)

    if fields_cfg.get("show_avatar", True):
        try:
            e.set_thumbnail(url=member.display_avatar.url)
        except Exception:
            pass

    footer = embed_cfg.get("footer", {}) or {}
    ft = (footer.get("text") or "").strip()
    if ft:
        e.set_footer(text=_render_vars(ft, member, guild))
    return e


class JoinLeave(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            cfg = load_guild_config(member.guild.id)
            jl = cfg.get("jl", {})
            if not jl.get("enabled", False):
                return
            if jl.get("filter", {}).get("ignore_bots", True) and member.bot:
                return

            ch_id = str(jl.get("channel_join", "")).strip()
            if not ch_id.isdigit():
                return
            ch = member.guild.get_channel(int(ch_id))
            if not ch:
                return

            emb_cfg = jl.get("join_embed", {}) or {}
            fields_cfg = jl.get("fields", {}) or {}
            embed = _make_embed(emb_cfg, member, member.guild, fields_cfg)
            await ch.send(embed=embed)
        except Exception:
            logger.exception("on_member_join failed")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            cfg = load_guild_config(member.guild.id)
            jl = cfg.get("jl", {})
            if not jl.get("enabled", False):
                return
            if jl.get("filter", {}).get("ignore_bots", True) and member.bot:
                return

            ch_id = str(jl.get("channel_leave", "")).strip()
            if not ch_id.isdigit():
                return
            ch = member.guild.get_channel(int(ch_id))
            if not ch:
                return

            emb_cfg = jl.get("leave_embed", {}) or {}
            fields_cfg = jl.get("fields", {}) or {}
            embed = _make_embed(emb_cfg, member, member.guild, fields_cfg)
            await ch.send(embed=embed)
        except Exception:
            logger.exception("on_member_remove failed")


async def setup(bot):
    await bot.add_cog(JoinLeave(bot))
