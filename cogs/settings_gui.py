import discord
from discord import app_commands
from discord.ext import commands

class SettingsGUI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="settings", description="Botの設定を変更します")
    @app_commands.checks.has_permissions(administrator=True)
    async def settings(self, interaction: discord.Interaction):
        conf = self.bot.get_guild_config(interaction.guild.id)
        embed = self.make_embed(interaction.guild, conf)
        view = SettingsView(conf)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    def make_embed(self, guild, conf):
        embed = discord.Embed(title=f"⚙️ {guild.name} 設定ダッシュボード", color=0x5865F2)
        f = conf["features"]
        embed.add_field(name="機能ステータス", value=f"チケット: {'✅' if f['ticket'] else '❌'}\n入退出: {'✅' if f['join_leave'] else '❌'}\nランキング: {'✅' if f['ranking'] else '❌'}", inline=False)
        return embed

class SettingsView(discord.ui.View):
    def __init__(self, conf):
        super().__init__()
        self.conf = conf

    @discord.ui.button(label="チケット機能 ON/OFF", style=discord.ButtonStyle.secondary)
    async def toggle_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.conf["features"]["ticket"] = not self.conf["features"]["ticket"]
        interaction.client.save_guild_config(interaction.guild.id, self.conf)
        await interaction.response.edit_message(embed=interaction.client.get_cog("SettingsGUI").make_embed(interaction.guild, self.conf))

async def setup(bot):
    await bot.add_cog(SettingsGUI(bot))