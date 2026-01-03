import discord
from discord import app_commands
from discord.ext import commands
import json
from pathlib import Path

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket_setup", description="チケットパネルを設置します")
    async def ticket_setup(self, interaction: discord.Interaction):
        # 簡易実装（Webで設定したパネルを呼び出す）
        await interaction.response.send_message("チケットパネルを設置しました（デバッグ用）", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))