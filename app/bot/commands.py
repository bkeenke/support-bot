from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)

from app.bot.utils.texts import SUPPORTED_LANGUAGES
from app.config import Config


async def setup(bot: Bot, config: Config) -> None:
    """
    Set up bot commands for various scopes and languages.

    :param bot: The Bot object.
    :param config: The Config object.
    """
    # Define bot commands for different languages
    commands = {
        "en": [
            BotCommand(command="start", description="Restart bot"),
        ],
        "ru": [
            BotCommand(command="start", description="Перезапустить бота"),
        ]
    }

    if len(SUPPORTED_LANGUAGES) > 1:
        # If there are more than one supported language, add commands for changing the language
        commands["en"].append(
            BotCommand(command="language", description="Change language"),
        )
        commands["ru"].append(
            BotCommand(command="language", description="Изменить язык"),
        )

    group_commands = {
        "en": [
            BotCommand(command="ban", description="Block/Unblock a user"),
            BotCommand(command="silent", description="Activate/Deactivate silent Mode"),
            BotCommand(command="information", description="User information"),
            BotCommand(command="show_old_messages", description="Show saved conversation history"),
        ],
        "ru": [
            BotCommand(command="ban", description="Заблокировать/Разблокировать пользователя"),
            BotCommand(command="silent", description="Активировать/Деактивировать тихий режим"),
            BotCommand(command="information", description="Информация о пользователе"),
            BotCommand(command="show_old_messages", description="Показать сохранённую переписку"),
        ]
    }

    admin_commands = {
        "en":
            commands["en"].copy() + [
                BotCommand(command="newsletter", description="Newsletter menu"),
                BotCommand(command="reload_faq", description="Reload FAQ cache"),
                BotCommand(command="autodelete", description="Topic auto-deletion (days, 0 = off)"),
            ],
        "ru":
            commands["ru"].copy() + [
                BotCommand(command="newsletter", description="Меню рассылки"),
                BotCommand(command="reload_faq", description="Сбросить кеш FAQ"),
                BotCommand(command="autodelete", description="Автоудаление топиков (дни, 0 = выкл)"),
            ],
    }

    for dev_id in [config.bot.DEV_ID] + config.bot.DEV_IDS:
        try:
            await bot.set_my_commands(
                commands=admin_commands["en"],
                scope=BotCommandScopeChat(chat_id=dev_id),
            )
            await bot.set_my_commands(
                commands=admin_commands["ru"],
                scope=BotCommandScopeChat(chat_id=dev_id),
                language_code="ru",
            )
        except TelegramBadRequest:
            raise ValueError(f"Chat with DEV_ID {dev_id} not found.")

    # Set commands for all private chats in English language
    await bot.set_my_commands(
        commands=commands["en"],
        scope=BotCommandScopeAllPrivateChats(),
    )
    # Set commands for all private chats in Russian language
    await bot.set_my_commands(
        commands=commands["ru"],
        scope=BotCommandScopeAllPrivateChats(),
        language_code="ru",
    )
    # Set commands for all group chats in English language
    await bot.set_my_commands(
        commands=group_commands["en"],
        scope=BotCommandScopeAllGroupChats(),
    )
    # Set commands for all group chats in Russian language
    await bot.set_my_commands(
        commands=group_commands["ru"],
        scope=BotCommandScopeAllGroupChats(),
        language_code="ru"
    )


async def delete(bot: Bot, config: Config) -> None:
    """
    Delete bot commands for various scopes and languages.

    :param config: The Config object.
    :param bot: The Bot object.
    """

    for dev_id in [config.bot.DEV_ID] + config.bot.DEV_IDS:
        try:
            await bot.delete_my_commands(
                scope=BotCommandScopeChat(chat_id=dev_id),
            )
            await bot.delete_my_commands(
                scope=BotCommandScopeChat(chat_id=dev_id),
                language_code="ru",
            )
        except TelegramBadRequest:
            raise ValueError(f"Chat with DEV_ID {dev_id} not found.")

    # Delete commands for all private chats in any language
    await bot.delete_my_commands(
        scope=BotCommandScopeAllPrivateChats(),
    )
    # Delete commands for all private chats in Russian language
    await bot.delete_my_commands(
        scope=BotCommandScopeAllPrivateChats(),
        language_code="ru",
    )
    # Delete commands for all group chats in any language
    await bot.delete_my_commands(
        scope=BotCommandScopeAllGroupChats(),
    )
    # Delete commands for all group chats in Russian language
    await bot.delete_my_commands(
        scope=BotCommandScopeAllGroupChats(),
        language_code="ru",
    )
