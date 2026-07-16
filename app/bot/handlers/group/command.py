from contextlib import suppress

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, MagicData
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.markdown import hcode, hbold

import asyncio

from app.bot.manager import Manager
from app.bot.utils.redis import RedisStorage
from app.bot.utils.topic_history import format_history

router_id = Router()
router_id.message.filter(
    F.chat.type.in_(["group", "supergroup"]),
)


@router_id.message(Command("id"))
async def handler(message: Message) -> None:
    """
    Sends chat ID in response to the /id command.

    :param message: Message object.
    :return: None
    """
    await message.reply(hcode(message.chat.id))


router = Router()
router.message.filter(
    F.message_thread_id.is_not(None),
    F.chat.type.in_(["group", "supergroup"]),
    MagicData(F.event_chat.id == F.config.bot.GROUP_ID),  # type: ignore
)


@router.message(Command("silent"))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """
    Toggles silent mode for a user in the group.
    If silent mode is disabled, it will be enabled, and vice versa.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    if user_data.message_silent_mode:
        text = manager.text_message.get("silent_mode_disabled")
        with suppress(TelegramBadRequest):
            # Reply with the specified text
            await message.reply(text)

            # Unpin the chat message with the silent mode status
            await message.bot.unpin_chat_message(
                chat_id=message.chat.id,
                message_id=user_data.message_silent_id,
            )

        user_data.message_silent_mode = False
        user_data.message_silent_id = None
    else:
        text = manager.text_message.get("silent_mode_enabled")
        with suppress(TelegramBadRequest):
            # Reply with the specified text
            msg = await message.reply(text)

            # Pin the chat message with the silent mode status
            await msg.pin(disable_notification=True)

        user_data.message_silent_mode = True
        user_data.message_silent_id = msg.message_id

    await redis.update_user(user_data.id, user_data)


@router.message(Command("information"))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """
    Sends user information in response to the /information command.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)

    if not user_data:
        # Web widget session topic
        session_id = await redis.get_session_id_by_thread(message.message_thread_id)
        if not session_id:
            return
        session = await redis.get_web_session(session_id)
        if not session:
            return
        lines = [
            "<b>Тип:</b> Web Widget",
            f"<b>SHM User ID:</b> <code>{session.external_id}</code>",
        ]
        if session.full_name:
            lines.append(f"<b>Имя:</b> {hbold(session.full_name)}")
        if session.login:
            lines.append(f"<b>Логин:</b> {session.login}")
        lines.append(f"<b>Дата создания:</b> {session.created_at}")
        text = "\n".join(lines)

        markup = None
        if manager.config.bot.SHM_API_URL:
            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="👤 SHM Info",
                    url=f"{manager.config.bot.SHM_API_URL}&q={session.external_id}",
                )
            ]])
        await message.reply(text, reply_markup=markup)
        return

    format_data = user_data.to_dict()
    format_data["full_name"] = hbold(format_data["full_name"])
    # Добавляем URL из конфигурации
    format_data["SHM_API_URL"] = manager.config.bot.SHM_API_URL
    text = manager.text_message.get("user_information")

    if user_data.email:
        shm_url = f"{manager.config.bot.SHM_API_URL}&q={user_data.email}"
        shm_url_text = "👤 SHM Info (email)"
    else:
        shm_url = f"{manager.config.bot.SHM_API_URL}&tgID={user_data.id}"
        shm_url_text = "👤 SHM Info (tgID)"
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=shm_url_text, url=shm_url)
    ]]) if manager.config.bot.SHM_API_URL else None

    # Reply with formatted user information
    await message.reply(text.format_map(format_data), reply_markup=markup)


@router.message(Command("show_old_messages"))
async def handler(message: Message, redis: RedisStorage) -> None:
    """
    Sends the saved conversation history into the topic. Useful after the
    old topic was auto-deleted and the user wrote again into a fresh one.

    :param message: Message object.
    :param redis: RedisStorage object.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    entries = await redis.get_history(user_data.id)
    if not entries:
        await message.reply("📭 Сохранённой переписки нет.")
        return

    chunks, shown = format_history(entries)
    header = f"📜 История переписки: {len(entries)} сообщ."
    if shown < len(entries):
        header += f" (показаны последние {shown})"
    await message.reply(header)

    for chunk in chunks:
        await message.bot.send_message(
            chat_id=message.chat.id,
            text=chunk,
            message_thread_id=message.message_thread_id,
        )
        await asyncio.sleep(0.5)


@router.message(Command(commands=["ban"]))
async def handler(message: Message, manager: Manager, redis: RedisStorage) -> None:
    """
    Toggles the ban status for a user in the group.
    If the user is banned, they will be unbanned, and vice versa.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :return: None
    """
    user_data = await redis.get_by_message_thread_id(message.message_thread_id)
    if not user_data: return None  # noqa

    if user_data.is_banned:
        user_data.is_banned = False
        text = manager.text_message.get("user_unblocked")
    else:
        user_data.is_banned = True
        text = manager.text_message.get("user_blocked")

    # Reply with the specified text
    await message.reply(text)
    await redis.update_user(user_data.id, user_data)
