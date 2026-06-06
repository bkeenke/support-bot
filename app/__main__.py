import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiohttp_socks import ProxyConnector
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .api import create_app, start_server
from .bot import commands
from .bot.handlers import include_routers
from .bot.middlewares import register_middlewares
from .bot.utils.redis import RedisStorage as BotRedisStorage
from .bot.utils.texts import load_faq_text
from .config import load_config, Config

logger = logging.getLogger(__name__)
from .logger import setup_logger


async def on_shutdown(
    apscheduler: AsyncIOScheduler,
    dispatcher: Dispatcher,
    config: Config,
    bot: Bot,
) -> None:
    """
    Shutdown event handler. This runs when the bot shuts down.

    :param apscheduler: AsyncIOScheduler: The apscheduler instance.
    :param dispatcher: Dispatcher: The bot dispatcher.
    :param config: Config: The config instance.
    :param bot: Bot: The bot instance.
    """
    # Stop apscheduler
    apscheduler.shutdown()
    # Delete commands and close storage when shutting down
    await commands.delete(bot, config)
    await dispatcher.storage.close()
    await bot.delete_webhook()
    await bot.session.close()


async def on_startup(
    apscheduler: AsyncIOScheduler,
    config: Config,
    bot: Bot,
) -> None:
    """
    Startup event handler. This runs when the bot starts up.

    :param apscheduler: AsyncIOScheduler: The apscheduler instance.
    :param config: Config: The config instance.
    :param bot: Bot: The bot instance.
    """
    # Start apscheduler
    apscheduler.start()
    # Load FAQ text from URL if configured
    if config.faq_ru_url:
        await load_faq_text("ru", config.faq_ru_url, proxy=config.proxy)
    if config.faq_en_url:
        await load_faq_text("en", config.faq_en_url, proxy=config.proxy)
    # Setup commands when starting up
    await commands.setup(bot, config)


async def main() -> None:
    """
    Main function that initializes the bot and starts the event loop.
    """
    # Load config
    config = load_config()

    # Initialize apscheduler
    job_store = RedisJobStore(
        host=config.redis.HOST,
        port=config.redis.PORT,
        db=config.redis.DB,
    )
    apscheduler = AsyncIOScheduler(
        jobstores={"default": job_store},
    )

    # Initialize Redis storage
    storage = RedisStorage.from_url(
        url=config.redis.dsn(),
    )

    # Create Bot and Dispatcher instances
    logger.info("Starting bot... proxy=%s", config.proxy or "none")

    _timeout = 15
    if config.proxy:
        if config.proxy.startswith("socks"):
            connector = ProxyConnector.from_url(config.proxy)
            session = AiohttpSession(connector=connector, timeout=_timeout)
        else:
            session = AiohttpSession(proxy=config.proxy, timeout=_timeout)
    else:
        session = AiohttpSession(timeout=_timeout)

    bot = Bot(
        token=config.bot.TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
        session=session,
    )
    dp = Dispatcher(
        apscheduler=apscheduler,
        storage=storage,
        config=config,
        bot=bot,
    )

    # Register startup handler
    dp.startup.register(on_startup)
    # Register shutdown handler
    dp.shutdown.register(on_shutdown)

    # Include routes
    include_routers(dp)
    # Register middlewares
    register_middlewares(
        dp, config=config, redis=storage.redis, apscheduler=apscheduler
    )

    # Start widget HTTP API
    bot_redis = BotRedisStorage(storage.redis)
    api_app = create_app(bot, bot_redis, config)
    api_runner = await start_server(api_app, config.api.HOST, config.api.PORT)

    # Start the bot
    logger.info("Connecting to Telegram API...")
    await bot.delete_webhook(request_timeout=15)
    me = await bot.get_me(request_timeout=15)
    logger.info("Bot started: @%s (id=%d)", me.username, me.id)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await api_runner.cleanup()


if __name__ == "__main__":
    # Set up logging
    setup_logger()
    # Run the bot
    asyncio.run(main())
