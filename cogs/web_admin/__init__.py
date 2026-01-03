import logging
from .manager import WebManager

logger = logging.getLogger("WebAdmin.Init")

async def setup(bot):
    logger.info("Initializing web_admin extension...")
    try:
        cog = WebManager(bot)
        await bot.add_cog(cog)
        # Webサーバーの起動メソッドを確実に呼び出す
        await cog.start_web_server()
        logger.info("web_admin setup complete.")
    except Exception as e:
        logger.error(f"Error during web_admin setup: {e}", exc_info=True)
        raise e