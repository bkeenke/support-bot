import asyncio
import logging
import time
import re

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

from app.config import Config
from .exceptions import CreateForumTopicException, NotEnoughRightsException, NotAForumException
from .redis import RedisStorage
from .redis.models import UserData


def _sanitize_topic_name(name: str) -> str:
    """
    Sanitize topic name to remove characters that Telegram doesn't accept.
    Telegram allows: letters, digits, spaces, hyphens, underscores, some Unicode.
    """
    # Remove leading/trailing whitespace
    name = name.strip()

    # Replace problematic characters with safe alternatives
    # Keep: a-z, A-Z, 0-9, space, hyphen, underscore, Cyrillic
    name = re.sub(r'[^\w\s\-а-яА-ЯёЁ]', '', name)

    # Collapse multiple spaces into one
    name = re.sub(r'\s+', ' ', name)

    # Truncate to 128 chars
    name = name[:128]

    # If empty after sanitization, use default
    return name or "User"


async def _is_topic_valid(bot: Bot, config: Config, message_thread_id: int) -> bool:
    """
    Validate that a forum topic still exists.
    We use reopen_forum_topic as a lightweight API probe: if topic is missing,
    Telegram returns BadRequest with thread/topic related text.
    """
    try:
        await bot.reopen_forum_topic(
            chat_id=config.bot.GROUP_ID,
            message_thread_id=message_thread_id,
        )
        return True
    except TelegramBadRequest as ex:
        error_msg = str(ex).lower()
        error_code = error_msg.replace(" ", "")
        # Topic does not exist anymore.
        if (
            "message thread not found" in error_msg
            or "topic was deleted" in error_msg
            or "topic_id_invalid" in error_code
            or "topic_deleted" in error_code
        ):
            return False
        # Topic exists but already open / unchanged.
        if (
            "not modified" in error_msg
            or "already open" in error_msg
            or "is not closed" in error_msg
            or "topic_not_modified" in error_code
            or "topic_already_open" in error_code
        ):
            return True
        # Unknown error: do not silently treat as valid.
        logging.debug("Topic probe failed for thread %s: %s", message_thread_id, ex)
        return False


async def get_or_create_forum_topic(
        bot: Bot,
        redis: RedisStorage,
        config: Config,
        user_data: UserData,
) -> int:
    if user_data.message_thread_id is not None:
        is_valid = await _is_topic_valid(bot, config, user_data.message_thread_id)
        if not is_valid:
            logging.warning(
                "Stored forum topic is invalid, resetting (user=%s, thread=%s)",
                user_data.id,
                user_data.message_thread_id,
            )
            user_data.message_thread_id = None
            await redis.update_user(user_data.id, user_data)

    if user_data.message_thread_id is None:
        try:
            # If message_thread_id is not found, create a forum topic
            name = (user_data.full_name or "User").strip()[:128] or "User"
            message_thread_id = await create_forum_topic(bot, config, name)
            if message_thread_id is None:
                raise CreateForumTopicException
            user_data.message_thread_id = message_thread_id
            await redis.update_user(user_data.id, user_data)

        except Exception as e:
            for dev_id in [config.bot.DEV_ID] + config.bot.DEV_IDS:
                await bot.send_message(dev_id, f"[create_forum_topic] user_id={user_data.id} name={user_data.full_name!r}\n{e}")
            logging.exception(e)
            raise

    if user_data.message_thread_id is None:
        raise CreateForumTopicException

    return user_data.message_thread_id


async def create_forum_topic(
    bot: Bot,
    config: Config,
    name: str,
    retry_count: int = 0,
    use_custom_icon: bool = True,
) -> int:
    """
    Creates a forum topic in the specified chat.

    :param bot: The Aiogram Bot instance.
    :param config: The configuration object.
    :param name: The name of the forum topic.
    :param retry_count: Internal retry counter for handling duplicate names.

    :return: The message thread ID of the created forum topic.
    :raises NotEnoughRightsException: If the bot doesn't have enough rights to create a forum topic.
    :raises CreateForumTopicException: If an error occurs while creating the forum topic.
    """
    # Sanitize the name to remove invalid characters
    display_name = _sanitize_topic_name(name)

    # On retry, append unique suffix to avoid name conflicts
    if retry_count > 0:
        unique_suffix = f"_{int(time.time() * 1000) % 100000}"
        display_name = (_sanitize_topic_name(name)[:128 - len(unique_suffix)] + unique_suffix).strip()

    try:
        # Attempt to create a forum topic
        create_args = {
            "chat_id": config.bot.GROUP_ID,
            "name": display_name,
            "request_timeout": 30,
        }
        if use_custom_icon and config.bot.BOT_EMOJI_ID:
            create_args["icon_custom_emoji_id"] = config.bot.BOT_EMOJI_ID

        forum_topic = await bot.create_forum_topic(**create_args)
        logging.debug(f"Forum topic created: {display_name} (thread_id={forum_topic.message_thread_id})")
        # Telegram may briefly lag before a brand-new topic accepts routed messages.
        await asyncio.sleep(0.4)
        return forum_topic.message_thread_id

    except TelegramRetryAfter as ex:
        # Handle Retry-After exception (rate limiting)
        logging.warning(f"Rate limited: {ex.message}, retrying after {ex.retry_after}s")
        await asyncio.sleep(ex.retry_after)
        return await create_forum_topic(bot, config, name, retry_count)

    except TelegramBadRequest as ex:
        error_msg = str(ex.message).lower()

        if "not enough rights" in error_msg:
            logging.error("Bot doesn't have enough rights to create forum topics")
            raise NotEnoughRightsException

        elif "not a forum" in error_msg:
            logging.error("Chat is not configured as a forum")
            raise NotAForumException

        elif "premium_account_required" in error_msg:
            # Some custom topic icons require premium/boosted capabilities.
            # Fallback to topic creation without icon.
            if use_custom_icon:
                logging.warning("Custom topic icon requires premium, retrying without icon")
                return await create_forum_topic(
                    bot,
                    config,
                    name,
                    retry_count=retry_count,
                    use_custom_icon=False,
                )
            raise CreateForumTopicException

        # If it's a duplicate name error and we haven't retried, try with unique suffix
        elif ("topic name is already taken" in error_msg or "already exists" in error_msg):
            if retry_count < 3:
                logging.warning(f"Topic name conflict (attempt {retry_count + 1}), retrying with unique suffix: {display_name}")
                return await create_forum_topic(
                    bot,
                    config,
                    name,
                    retry_count + 1,
                    use_custom_icon=use_custom_icon,
                )

        # Log the actual error for debugging
        logging.error(f"Telegram error creating forum topic '{display_name}': {ex.message}")
        raise CreateForumTopicException

    except Exception as ex:
        logging.error(f"Unexpected error creating forum topic: {type(ex).__name__}: {ex}")
        raise CreateForumTopicException from ex
