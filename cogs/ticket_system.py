import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import time
import io

class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket-panel", description="チケット作成パネルを設置")
    async def ticket_panel(self, interaction: discord.Interaction):
        conf = self.bot.get_guild_config(interaction.guild.id)
        if not conf["features"]["ticket"]:
            return await interaction.response.send_message("チケット機能が有効ではありません。", ephemeral=True)
        
        embed = discord.Embed(title="サポートチケット", description="ボタンを押すと専用チャンネルが作成されます。", color=0x00ff00)
        view = TicketCreateView()
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("設置しました", ephemeral=True)

class TicketCreateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケット作成", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        channel = await interaction.guild.create_text_channel(name=f"ticket-{interaction.user.name}", overwrites=overwrites)
        
        embed = discord.Embed(title="チケット", description="運営が対応するまでお待ちください。", color=0x3498db)
        await channel.send(embed=embed, view=TicketCloseView())
        await interaction.response.send_message(f"チャンネルを作成しました: {channel.mention}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # HTMLログの生成
        messages = []
        async for msg in interaction.channel.history(limit=1000, oldest_first=True):
            messages.append(f"<div><b>{msg.author}</b>: {msg.content} <small>{msg.created_at}</small></div>")
        
        html_content = f"<html><body style='font-family:sans-serif;'><h1>Ticket Log: {interaction.channel.name}</h1>" + "".join(messages) + "</body></html>"
        
        # ログ送信
        conf = interaction.client.get_guild_config(interaction.guild.id)
        log_ch_id = conf["ticket"]["log_channel_id"]
        
        file = discord.File(io.BytesIO(html_content.encode()), filename=f"{interaction.channel.name}.html")
        
        if log_ch_id:
            log_ch = interaction.guild.get_channel(int(log_ch_id))
            if log_ch:
                await log_ch.send(f"チケット終了ログ: {interaction.channel.name}", file=file)
        
        await interaction.channel.delete()

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))