import asyncio
import json
import logging
import time
import math
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import load_guild_config, save_guild_config

logger = logging.getLogger("Ranking")

DATA_DIR = Path("data/ranking")
DATA_DIR.mkdir(parents=True, exist_ok=True)

def _p_text(gid): return DATA_DIR / ("text_{}.json".format(gid))
def _p_vc(gid): return DATA_DIR / ("vc_{}.json".format(gid))

def _load_json(p):
    if not p.exists():
        p.write_text("{}", encoding="utf-8")
    try:
        raw = p.read_text(encoding="utf-8").strip()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}

def _save_json(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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

def _fmt_vc(seconds):
    seconds = int(seconds or 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return "{}h {}m".format(h, m)

def _top5(d):
    items = [(k, d.get(k, 0)) for k in d.keys()]
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:5]

def _calc_level_from_xp(xp):
    """
    XPテーブル:
      level = floor(sqrt(xp/100))
      next  = (level+1)^2 * 100
    """
    xp = max(0, int(xp))
    level = int(math.floor(math.sqrt(xp / 100.0)))
    next_xp = int((level + 1) ** 2 * 100)
    return level, xp, next_xp

def _apply_vars(text, mapping):
    s = str(text or "")
    for k, v in mapping.items():
        s = s.replace("{" + k + "}", str(v))
    return s


class Ranking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._vc_sessions = {}  # (gid, uid) -> join_time
        self._task = self.bot.loop.create_task(self._leaderboard_loop())

    def cog_unload(self):
        try:
            if self._task:
                self._task.cancel()
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        gid = message.guild.id
        uid = str(message.author.id)

        p = _p_text(gid)
        data = _load_json(p)
        data[uid] = int(data.get(uid, 0)) + 1
        _save_json(p, data)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild:
            return
        gid = member.guild.id
        uid = str(member.id)
        key = (gid, uid)

        if before.channel is None and after.channel is not None:
            self._vc_sessions[key] = time.time()
            return

        if before.channel is not None and after.channel is None:
            start = self._vc_sessions.pop(key, None)
            if start:
                sec = int(time.time() - start)
                p = _p_vc(gid)
                data = _load_json(p)
                data[uid] = int(data.get(uid, 0)) + sec
                _save_json(p, data)
            return

        if before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            start = self._vc_sessions.get(key)
            if start:
                sec = int(time.time() - start)
                p = _p_vc(gid)
                data = _load_json(p)
                data[uid] = int(data.get(uid, 0)) + sec
                _save_json(p, data)
            self._vc_sessions[key] = time.time()

    @app_commands.command(name="rank", description="あなたのランク情報を表示します（Embed）")
    async def rank_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("サーバー内で実行してください。", ephemeral=True)
            return

        cfg = load_guild_config(interaction.guild.id)
        if not cfg.get("rank", {}).get("enabled", True):
            await interaction.response.send_message("Rankingは無効です。", ephemeral=True)
            return

        gid = interaction.guild.id
        uid = str(interaction.user.id)

        text = _load_json(_p_text(gid))
        vc = _load_json(_p_vc(gid))

        messages = int(text.get(uid, 0))
        vc_sec = int(vc.get(uid, 0))

        # ✅ 指定変数に合わせる：xp/level/next/messages
        level, xp, next_xp = _calc_level_from_xp(messages)

        # 既存互換のために追加変数も用意
        overall_score = int((messages + (vc_sec // 60)) / 2)

        mapping = {
            "user": interaction.user.mention,
            "username": interaction.user.display_name,

            "level": level,
            "xp": xp,
            "next": next_xp,
            "messages": messages,

            "text_count": messages,
            "vc_time": _fmt_vc(vc_sec),
            "overall_score": overall_score
        }

        emb_cfg = cfg.get("rank", {}).get("embed", {}) or {}
        title = _apply_vars(emb_cfg.get("title", "ランク - {username}"), mapping)
        desc = _apply_vars(emb_cfg.get("description", ""), mapping)

        e = discord.Embed(
            title=title,
            description=desc,
            color=_parse_color(emb_cfg.get("color", "#6D7CFF"), discord.Color.blurple())
        )

        for f in (emb_cfg.get("fields", []) or []):
            name = _apply_vars(f.get("name", ""), mapping)
            value = _apply_vars(f.get("value", ""), mapping)
            e.add_field(name=name, value=value, inline=bool(f.get("inline", True)))

        footer = (emb_cfg.get("footer", {}) or {}).get("text", "")
        if footer:
            e.set_footer(text=_apply_vars(footer, mapping))

        await interaction.response.send_message(embed=e, ephemeral=True)

    def _build_leaderboard_embed(self, guild):
        gid = guild.id
        text = _load_json(_p_text(gid))
        vc = _load_json(_p_vc(gid))

        overall_map = {}
        for uid in set(list(text.keys()) + list(vc.keys())):
            t = int(text.get(uid, 0))
            vmin = int(int(vc.get(uid, 0)) // 60)
            overall_map[uid] = int((t + vmin) / 2)

        top_text = _top5(text)
        top_vc = _top5(vc)
        top_overall = _top5(overall_map)

        def fmt_list(items, mode):
            lines = []
            for i, (uid, val) in enumerate(items, start=1):
                m = guild.get_member(int(uid)) if str(uid).isdigit() else None
                name = m.display_name if m else "User {}".format(uid)
                s = _fmt_vc(val) if mode == "vc" else str(val)
                lines.append("`#{}` {} — **{}**".format(i, name, s))
            return "\n".join(lines) if lines else "（データなし）"

        e = discord.Embed(
            title="🏆 Leaderboard Top5",
            description="テキスト / VC / 総合（平均）を自動更新します。",
            color=discord.Color.blurple()
        )
        e.add_field(name="💬 テキスト Top5", value=fmt_list(top_text, "text"), inline=False)
        e.add_field(name="🎙️ VC Top5", value=fmt_list(top_vc, "vc"), inline=False)
        e.add_field(name="✨ 総合 Top5", value=fmt_list(top_overall, "overall"), inline=False)
        e.set_footer(text="自動更新中")
        return e

    async def deploy_or_update_leaderboard(self, guild, force_send=False):
        cfg = load_guild_config(guild.id)
        lb = cfg.get("rank", {}).get("leaderboard", {}) or {}
        if not lb.get("enabled", False) and not force_send:
            return None

        ch_id = str(lb.get("channel_id", "")).strip()
        if not ch_id.isdigit():
            return None
        ch = guild.get_channel(int(ch_id))
        if not ch:
            return None

        embed = self._build_leaderboard_embed(guild)

        msg_id = str(lb.get("message_id", "")).strip()
        if msg_id.isdigit() and not force_send:
            try:
                m = await ch.fetch_message(int(msg_id))
                await m.edit(embed=embed)
                return m
            except Exception:
                pass

        m = await ch.send(embed=embed)
        cfg["rank"]["leaderboard"]["message_id"] = str(m.id)
        save_guild_config(guild.id, cfg)
        return m

    async def _leaderboard_loop(self):
        await self.bot.wait_until_ready()
        self._lb_last = {}
        while not self.bot.is_closed():
            try:
                now = time.time()
                for g in list(self.bot.guilds):
                    cfg = load_guild_config(g.id)
                    lb = cfg.get("rank", {}).get("leaderboard", {}) or {}
                    if not lb.get("enabled", False):
                        continue
                    interval = int(lb.get("interval_minutes", 10))
                    last = float(self._lb_last.get(g.id, 0))
                    if now - last < interval * 60:
                        continue
                    await self.deploy_or_update_leaderboard(g, force_send=False)
                    self._lb_last[g.id] = now
            except Exception:
                logger.exception("leaderboard loop error")
            await asyncio.sleep(30)


async def setup(bot):
    await bot.add_cog(Ranking(bot))
