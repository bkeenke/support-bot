import logging

import aiohttp
from aiohttp import web
from aiogram import Bot

from app.bot.utils.redis import RedisStorage
from app.config import Config
from .widget import router

logger = logging.getLogger(__name__)


async def _on_startup(app: web.Application) -> None:
    app["http"] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))


async def _on_cleanup(app: web.Application) -> None:
    await app["http"].close()


def create_app(bot: Bot, redis_storage: RedisStorage, config: Config) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app["rs"] = redis_storage
    app["config"] = config
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    app.router.add_routes(router)
    return app


async def start_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Widget API listening on %s:%s", host, port)
    return runner
