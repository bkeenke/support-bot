from aiogram import Router, F
from aiogram.filters import Command, MagicData
from aiogram.types import Message
from aiogram_newsletter.manager import ANManager

from app.bot.handlers.private.windows import Window
from app.bot.manager import Manager
from app.bot.utils.create_forum_topic import get_or_create_forum_topic
from app.bot.utils.redis import RedisStorage
from app.bot.utils.redis.models import UserData
from app.bot.utils.texts import clear_faq_cache, load_faq_text

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(Command("start"))
async def handler(
        message: Message,
        manager: Manager,
        redis: RedisStorage,
        user_data: UserData,
) -> None:
    """
    Handles the /start command.

    If the user has already selected a language, displays the main menu window.
    Otherwise, prompts the user to select a language.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param user_data: UserData object.
    :return: None
    """
    if user_data.language_code:
        await Window.main_menu(manager)
    else:
        await Window.select_language(manager)
    await manager.delete_message(message)

    # Create the forum topic
    await get_or_create_forum_topic(message.bot, redis, manager.config, user_data)


@router.message(Command("language"))
async def handler(message: Message, manager: Manager, user_data: UserData) -> None:
    """
    Handles the /language command.

    If the user has already selected a language, prompts the user to select a new language.
    Otherwise, prompts the user to select a language.

    :param message: Message object.
    :param manager: Manager object.
    :param user_data: UserData object.
    :return: None
    """
    if user_data.language_code:
        await Window.change_language(manager)
    else:
        await Window.select_language(manager)
    await manager.delete_message(message)


@router.message(Command("source"))
async def handler(message: Message, manager: Manager) -> None:
    """
    Handles the /source command.

    :param message: Message object.
    :param manager: Manager object.
    :return: None
    """
    text = manager.text_message.get("source")
    await manager.send_message(text)
    await manager.delete_message(message)


@router.message(
    Command("reload_faq"),
    MagicData(
        (F.event_from_user.id == F.config.bot.DEV_ID) |
        F.event_from_user.id.in_(F.config.bot.DEV_IDS)
    ),
)
async def handler(message: Message, manager: Manager) -> None:
    if not manager.config.faq_ru_url and not manager.config.faq_en_url:
        await message.answer("FAQ_TEXT_URL and FAQ_EN_TEXT_URL are not configured.")
        return
    clear_faq_cache()
    if manager.config.faq_ru_url:
        await load_faq_text("ru", manager.config.faq_ru_url, proxy=manager.config.proxy)
    if manager.config.faq_en_url:
        await load_faq_text("en", manager.config.faq_en_url, proxy=manager.config.proxy)
    await message.answer("FAQ cache reloaded.")
    await manager.delete_message(message)


@router.message(
    Command("newsletter"),
    MagicData(
        (F.event_from_user.id == F.config.bot.DEV_ID) |
        F.event_from_user.id.in_(F.config.bot.DEV_IDS)
    ),
)
async def handler(
        message: Message,
        manager: Manager,
        an_manager: ANManager,
        redis: RedisStorage,
) -> None:
    """
    Handles the /newsletter command.

    :param message: Message object.
    :param manager: Manager object.
    :param redis: RedisStorage object.
    :param an_manager: Manager object from aiogram_newsletter.
    :return: None
    """
    users_ids = await redis.get_all_users_ids()
    await an_manager.newsletter_menu(users_ids, Window.main_menu)
    await manager.delete_message(message)
