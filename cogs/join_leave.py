import discord
from discord.ext import commands
import json
import os

class JoinLeave(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_config(self, guild_id):
        path = f"settings/guilds/{guild_id}/config.json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            default = {
                "join_enabled": False,
                "leave_enabled": False,
                "channel_id": None,
                "join_message": "ようこそ {user} さん！ {guild}へ。 現在 {member_count}人目です。",
                "leave_message": "{user} さんが退出しました。"
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=4, ensure_ascii=False)
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        conf = self.get_config(member.guild.id)
        if not conf["join_enabled"] or not conf["channel_id"]:
            return
        channel = member.guild.get_channel(int(conf["channel_id"]))
        if channel:
            msg = conf["join_message"].format(
                user=member.mention, 
                guild=member.guild.name, 
                member_count=member.guild.member_count
            )
            await channel.send(msg)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        conf = self.get_config(member.guild.id)
        if not conf["leave_enabled"] or not conf["channel_id"]:
            return
        channel = member.guild.get_channel(int(conf["channel_id"]))
        if channel:
            msg = conf["leave_message"].format(
                user=member.name, 
                guild=member.guild.name, 
                member_count=member.guild.member_count
            )
            await channel.send(msg)

async def setup(bot):
    await bot.add_cog(JoinLeave(bot))