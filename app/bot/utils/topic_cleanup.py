import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from app.config import Config
from .redis import RedisStorage

logger = logging.getLogger(__name__)

# How often the cleanup sweep runs.
CLEANUP_INTERVAL = 3600
# Delay before the first sweep after startup.
STARTUP_DELAY = 60


async def _delete_topic(bot: Bot, config: Config, message_thread_id: int) -> bool:
    """
    Delete a forum topic. Returns True if the topic is gone
    (deleted now or already missing), False on any other error.
    """
    try:
        await bot.delete_forum_topic(
            chat_id=config.bot.GROUP_ID,
            message_thread_id=message_thread_id,
        )
        return True
    except TelegramRetryAfter as ex:
        await asyncio.sleep(ex.retry_after)
        return await _delete_topic(bot, config, message_thread_id)
    except TelegramBadRequest as ex:
        error_msg = str(ex).lower()
        if "message thread not found" in error_msg or "topic" in error_msg and "deleted" in error_msg:
            return True  # already gone — still clear the mapping
        logger.warning("Failed to delete topic %s: %s", message_thread_id, ex)
        return False


async def cleanup_old_topics(bot: Bot, redis: RedisStorage, config: Config) -> None:
    """
    Delete forum topics whose last activity is older than the configured
    number of days. Message history (history:{user_id}) is kept, so the
    conversation can be restored later via /show_old_messages.
    """
    ttl_days = await redis.get_topic_ttl_days()
    if ttl_days <= 0:
        return

    cutoff = int(time.time()) - ttl_days * 86400
    deleted = 0

    for user_id in await redis.get_all_users_ids():
        user_data = await redis.get_user(user_id)
        if not user_data or user_data.message_thread_id is None:
            continue

        last_activity = await redis.get_last_activity(user_id)
        if last_activity is None:
            # No activity recorded yet (user predates activity tracking).
            # Start counting from now instead of deleting blindly.
            await redis.set_last_activity(user_id, int(time.time()))
            continue

        if last_activity > cutoff:
            continue

        thread_id = user_data.message_thread_id
        if not await _delete_topic(bot, config, thread_id):
            continue

        user_data.message_thread_id = None
        await redis.update_user(user_id, user_data)
        await redis.redis.delete(
            f"{redis.NAME}_thread:{thread_id}",
            f"topic_valid:{thread_id}",
        )
        deleted += 1
        logger.info("Auto-deleted topic %s (user=%s, inactive > %s days)", thread_id, user_id, ttl_days)
        # Be gentle with the Telegram API.
        await asyncio.sleep(1)

    if deleted:
        logger.info("Topic cleanup finished: %s topic(s) deleted", deleted)


async def topic_cleanup_loop(bot: Bot, redis: RedisStorage, config: Config) -> None:
    """Background task: periodically run the topic cleanup sweep."""
    await asyncio.sleep(STARTUP_DELAY)
    while True:
        try:
            await cleanup_old_topics(bot, redis, config)
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            logger.exception("Topic cleanup sweep failed: %s", ex)
        await asyncio.sleep(CLEANUP_INTERVAL)
