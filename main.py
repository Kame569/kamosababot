import discord
from discord.ext import commands
import os
import json
import logging
import datetime
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BotMain")
load_dotenv()

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)
        self.web_started = False

    def update_stats(self, guild_id, key):
        today = datetime.date.today().isoformat()
        path = Path(f"data/stats/{guild_id}.json")
        path.parent.mkdir(parents=True, exist_ok=True)

        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if today not in data:
            data[today] = {"messages": 0, "joins": 0, "leaves": 0}

        data[today][key] += 1
        path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")

    async def setup_hook(self):
        for d in ["settings/guilds", "data/tickets", "data/stats", "data/ranking"]:
            Path(d).mkdir(parents=True, exist_ok=True)

        # ✅ Webは cogs.web_admin をロード（__init__.pyのsetupが起動する）
        exts = [
            "cogs.web_admin",
            "cogs.ticket_system",
            "cogs.join_leave",
            "cogs.ranking",
        ]
        for ext in exts:
            await self.load_extension(ext)

    async def on_ready(self):
        logger.info(f"Logged in as {self.user}")
        try:
            await self.tree.sync()
        except Exception:
            logger.exception("tree.sync failed")

    async def on_message(self, message):
        if not message.author.bot and message.guild:
            self.update_stats(message.guild.id, "messages")
        await self.process_commands(message)

    async def on_member_join(self, member):
        self.update_stats(member.guild.id, "joins")

    async def on_member_remove(self, member):
        self.update_stats(member.guild.id, "leaves")

if __name__ == "__main__":
    bot = MyBot()
    bot.run(os.getenv("DISCORD_TOKEN"))
