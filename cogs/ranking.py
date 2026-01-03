import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import time

class Ranking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vc_start_times = {} # {member_id: start_time}
        self.save_data.start()

    def get_rank_path(self, guild_id, type):
        path = f"settings/guilds/{guild_id}/rank_{type}.json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def load_rank_data(self, guild_id, type):
        path = self.get_rank_path(guild_id, type)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_rank_data(self, guild_id, type, data):
        path = self.get_rank_path(guild_id, type)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        data = self.load_rank_data(message.guild.id, "message")
        uid = str(message.author.id)
        data[uid] = data.get(uid, 0) + 1
        self.save_rank_data(message.guild.id, "message", data)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        uid = member.id
        # VC参加
        if before.channel is None and after.channel is not None:
            self.vc_start_times[uid] = time.time()
        # VC退出
        elif before.channel is not None and after.channel is None:
            if uid in self.vc_start_times:
                duration = int(time.time() - self.vc_start_times.pop(uid))
                data = self.load_rank_data(member.guild.id, "vc")
                suid = str(uid)
                data[suid] = data.get(suid, 0) + duration
                self.save_rank_data(member.guild.id, "vc", data)

    @tasks.loop(minutes=5)
    async def save_data(self):
        # VC継続中の人を一時保存（Bot落ち対策などが必要な場合はここで実装）
        pass

    @app_commands.command(name="rank-board", description="ランキングを表示します")
    async def rank_board(self, interaction: discord.Interaction):
        m_data = self.load_rank_data(interaction.guild.id, "message")
        v_data = self.load_rank_data(interaction.guild.id, "vc")
        
        # ソート
        m_sorted = sorted(m_data.items(), key=lambda x: x[1], reverse=True)[:5]
        v_sorted = sorted(v_data.items(), key=lambda x: x[1], reverse=True)[:5]

        embed = discord.Embed(title=f"📊 {interaction.guild.name} ランキング", color=discord.Color.gold())
        
        m_txt = "\n".join([f"<@{u}>: {c}回" for u, c in m_sorted]) or "データなし"
        embed.add_field(name="💬 発言数TOP5", value=m_txt, inline=False)
        
        v_txt = "\n".join([f"<@{u}>: {c//60}分" for u, c in v_sorted]) or "データなし"
        embed.add_field(name="🎙️ VC時間TOP5", value=v_txt, inline=False)

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Ranking(bot))