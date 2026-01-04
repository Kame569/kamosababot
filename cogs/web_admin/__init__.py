import logging
from discord.ext import commands
from .manager import WebManager

logger = logging.getLogger("WebAdmin")


async def setup(bot: commands.Bot):
    cog = WebManager(bot)
    await bot.add_cog(cog)

    if not hasattr(bot, "web_started"):
        bot.web_started = False

    if not bot.web_started:
        bot.web_started = True

        async def _starter():
            await bot.wait_until_ready()
            try:
                await cog.start_web_server()
                logger.info("[WEB] started")
            except Exception:
                logger.exception("[WEB] failed to start")

        bot.loop.create_task(_starter())
