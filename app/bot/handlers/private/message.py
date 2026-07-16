import asyncio
import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.types import Message

from app.bot.manager import Manager
from app.bot.types.album import Album
from app.bot.utils.create_forum_topic import (
    create_forum_topic,
    get_or_create_forum_topic,
)
from app.bot.utils.redis import RedisStorage
from app.bot.utils.redis.models import UserData
from app.bot.utils.topic_history import log_message

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == "private", StateFilter(None))


@router.edited_message()
async def handle_edited_message(message: Message, manager: Manager) -> None:
    """
    Handle edited messages.

    :param message: The edited message.
    :param manager: Manager object.
    :return: None
    """
    # Get the text for the edited message
    text = manager.text_message.get("message_edited")
    # Reply to the edited message with the specified text
    msg = await message.reply(text)
    # Wait for 5 seconds before deleting the reply
    await asyncio.sleep(5)
    # Delete the reply to the edited message
    await msg.delete()


@router.message(F.media_group_id)
@router.message(F.media_group_id.is_(None))
async def handle_incoming_message(
        message: Message,
        manager: Manager,
        redis: RedisStorage,
        user_data: UserData,
        album: Album | None = None,
) -> None:
    """
    Handles incoming messages and copies them to the forum topic.
    If the user is banned, the messages are ignored.

    :param message: The incoming message.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param user_data: UserData object.
    :param album: Album object or None.
    :return: None
    """
    # Check if the user is banned
    if user_data.is_banned:
        return

    async def copy_message_to_topic(message_thread_id: int) -> None:
        """
        Copies the message or album to the forum topic.
        If no album is provided, the message is copied. Otherwise, the album is copied.
        """
        if not album:
            await message.forward(
                chat_id=manager.config.bot.GROUP_ID,
                message_thread_id=message_thread_id,
            )
        else:
            await album.copy_to(
                chat_id=manager.config.bot.GROUP_ID,
                message_thread_id=message_thread_id,
            )

    for attempt in range(2):
        message_thread_id = await get_or_create_forum_topic(
            message.bot,
            redis,
            manager.config,
            user_data,
        )
        try:
            await copy_message_to_topic(message_thread_id)
            break
        except TelegramBadRequest as ex:
            error_msg = str(ex).lower()
            logger.warning(
                "Send to topic failed (user=%s, thread=%s, attempt=%s): %s",
                user_data.id,
                message_thread_id,
                attempt + 1,
                ex,
            )
            # Telegram may return different texts for deleted/invalid topics.
            if (
                "message thread" in error_msg
                or "topic" in error_msg
                or "forum" in error_msg
            ) and attempt == 0:
                user_data.message_thread_id = None
                await redis.update_user(user_data.id, user_data)
                continue
            raise
        except TelegramAPIError as ex:
            logger.error(
                "Telegram API error while forwarding (user=%s, thread=%s): %s",
                user_data.id,
                message_thread_id,
                ex,
            )
            raise

    # Save the message to the history (survives topic auto-deletion)
    for msg in (album.messages if album else [message]):
        await log_message(redis, user_data.id, msg, "user")

    # Send a confirmation message to the user
    text = manager.text_message.get("message_sent")
    # Reply to the edited message with the specified text
    msg = await message.reply(text)
    # Wait for 5 seconds before deleting the reply
    await asyncio.sleep(5)
    # Delete the reply to the edited message
    await msg.delete()
