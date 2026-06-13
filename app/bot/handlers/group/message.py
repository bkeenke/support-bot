import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import aiohttp
from aiogram import Router, F
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import MagicData
from aiogram.types import Message
from aiogram.utils.markdown import hlink

from app.bot.manager import Manager
from app.bot.types.album import Album
from app.bot.utils.redis import RedisStorage

logger = logging.getLogger(__name__)
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "/app/media"))

router = Router()
router.message.filter(
    MagicData(F.event_chat.id == F.config.bot.GROUP_ID),  # type: ignore
    F.chat.type.in_(["group", "supergroup"]),
    F.message_thread_id.is_not(None),
)


@router.message(F.forum_topic_created)
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    await asyncio.sleep(3)
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    # Generate a URL for the user's profile
    url = f"https://t.me/{user_data.username[1:]}" if user_data.username != "-" else f"tg://user?id={user_data.id}"

    # Get the appropriate text based on the user's state
    text = manager.text_message.get("user_started_bot")

    message = await message.bot.send_message(
        chat_id=manager.config.bot.GROUP_ID,
        text=text.format(name=hlink(user_data.full_name, url)),
        message_thread_id=user_data.message_thread_id
    )

    # Pin the message
    await message.pin()


@router.message(F.pinned_message | F.forum_topic_edited | F.forum_topic_closed | F.forum_topic_reopened)
async def handler(message: Message) -> None:
    """
    Delete service messages such as pinned, edited, closed, or reopened forum topics.

    :param message: Message object.
    :return: None
    """
    await message.delete()


async def _save_local(bot, session_id: str, file_id: str, ext: str = "bin") -> str | None:
    try:
        folder = MEDIA_DIR / session_id
        folder.mkdir(parents=True, exist_ok=True)
        tg_file = await bot.get_file(file_id)
        filename = f"{uuid.uuid4().hex}.{ext}"
        await bot.download_file(tg_file.file_path, destination=folder / filename)
        return filename
    except Exception as exc:
        logger.error("_save_local failed session=%s: %s: %s", session_id, type(exc).__name__, exc)
        return None


async def _push_to_web_inbox(redis: RedisStorage, session_id: str, message: Message) -> None:
    entry: dict = {"ts": int(time.time()), "from": "support"}

    if message.text:
        entry["text"] = message.text
    elif message.caption:
        entry["text"] = message.caption

    if message.photo:
        file_id = message.photo[-1].file_id
        filename = await _save_local(message.bot, session_id, file_id, "jpg")
        if filename:
            entry["local_photo"] = filename
        else:
            entry["photo_file_id"] = file_id  # fallback: proxy from Telegram
    elif message.document:
        file_id = message.document.file_id
        orig = message.document.file_name or "file.bin"
        ext = orig.rsplit(".", 1)[-1] if "." in orig else "bin"
        filename = await _save_local(message.bot, session_id, file_id, ext)
        if filename:
            entry["local_doc"] = filename
            entry["file_name"] = orig
        else:
            entry["doc_file_id"] = file_id  # fallback
            entry["file_name"] = orig

    await redis.push_web_inbox(session_id, entry)


async def _fire_read_webhook(
    url: str, user_id: str, text: str,
    redis: RedisStorage, session_id: str, msg_index: int, delay: int,
    secret: str | None = None,
) -> None:
    await asyncio.sleep(delay)
    cursor = await redis.get_read_cursor(session_id)
    if cursor > msg_index:
        return  # user read it during the delay
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        headers = {"x-secret": secret} if secret else {}
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.post(url, json={"user_id": user_id, "text": text}, headers=headers) as r:
                if r.status >= 400:
                    logger.warning("read_webhook returned %s for user_id=%s", r.status, user_id)
    except Exception as exc:
        logger.warning("read_webhook failed for user_id=%s: %s", user_id, exc)


@router.message(F.media_group_id, F.from_user[F.is_bot.is_(False)])
@router.message(F.media_group_id.is_(None), F.from_user[F.is_bot.is_(False)])
async def handler(message: Message, manager: Manager, redis: RedisStorage, album: Optional[Album] = None) -> None:
    """
    Handles user messages and sends them to the respective user.
    If silent mode is enabled for the user, the messages are ignored.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param album: Album object or None.
    :return: None
    """
    # Web widget session — push reply to inbox instead of forwarding to Telegram
    session_id = await redis.get_session_id_by_thread(message.message_thread_id)
    if session_id:
        await _push_to_web_inbox(redis, session_id, message)
        webhook_url = manager.config.api.READ_WEBHOOK_URL
        if webhook_url:
            total = await redis.get_web_inbox_len(session_id)
            session = await redis.get_web_session(session_id)
            if session:
                text = message.text or message.caption or ""
                delay = manager.config.api.READ_WEBHOOK_DELAY
                asyncio.create_task(_fire_read_webhook(
                    webhook_url, session.external_id, text,
                    redis, session_id, total - 1, delay,
                    manager.config.api.API_SECRET_KEY,
                ))
        return

    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    if user_data.message_silent_mode:
        # If silent mode is enabled, ignore all messages.
        return

    text = manager.text_message.get("message_sent_to_user")

    try:
        if not album:
            await message.copy_to(chat_id=user_data.id)
        else:
            await album.copy_to(chat_id=user_data.id)

    except TelegramAPIError as ex:
        if "blocked" in ex.message:
            text = manager.text_message.get("blocked_by_user")

    except (Exception,):
        text = manager.text_message.get("message_not_sent")

    # Reply to the edited message with the specified text
    msg = await message.reply(text)
    # Wait for 5 seconds before deleting the reply
    await asyncio.sleep(5)
    # Delete the reply to the edited message
    await msg.delete()
