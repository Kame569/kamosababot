import discord
from discord.ext import commands
import os
import json
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.initial_extensions = [
            'cogs.ticket_system',
            'cogs.join_leave',
            'cogs.ranking',
            'cogs.settings_gui',
            'cogs.web_admin'
        ]

    async def setup_hook(self):
        for ext in self.initial_extensions:
            await self.load_extension(ext)
        await self.tree.sync()

    def get_guild_config(self, guild_id):
        """全Cog共通で使用する設定読み込み関数"""
        path = f"settings/guilds/{guild_id}/config.json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            default = {
                "features": {"ticket": False, "join_leave": False, "ranking": False},
                "join_leave": {"channel_id": None, "join_msg": "Welcome {user}!", "leave_msg": "Bye {user}"},
                "ticket": {"log_channel_id": None, "category_id": None},
                "ranking": {"channel_id": None, "interval": 5}
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=4, ensure_ascii=False)
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_guild_config(self, guild_id, data):
        path = f"settings/guilds/{guild_id}/config.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

bot = MyBot()
bot.run(os.getenv("DISCORD_TOKEN"))