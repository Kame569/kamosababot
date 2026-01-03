import discord
from discord.ext import commands
import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotMain")
load_dotenv()

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.web_started = False

    async def setup_hook(self):
        # 必須ディレクトリ作成
        for d in ["settings/guilds", "data/tickets", "data/logs", "data/ranking"]:
            Path(d).mkdir(parents=True, exist_ok=True)

        # Cogsロード
        extensions = [
            "cogs.web_admin",
            "cogs.ticket_system",
            "cogs.join_leave",
            "cogs.ranking"
        ]
        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"Extension loaded: {ext}")
            except Exception as e:
                logger.error(f"Failed to load {ext}: {e}", exc_info=True)

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.tree.sync()
        logger.info("Slash commands synced.")

if __name__ == "__main__":
    bot = MyBot()
    bot.run(os.getenv("DISCORD_TOKEN"))