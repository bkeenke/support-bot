import logging
from abc import abstractmethod, ABCMeta
from html.parser import HTMLParser

import aiohttp
from aiogram.utils.markdown import hbold

logger = logging.getLogger(__name__)

# Telegram-supported HTML tags
_ALLOWED_TAGS = {"b", "i", "u", "s", "a", "code", "pre", "blockquote", "tg-spoiler", "tg-emoji"}


class _TelegramHTMLSanitizer(HTMLParser):
    """Strip tags not supported by Telegram HTML parser and auto-close unclosed tags."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._result: list[str] = []
        self._open_tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _ALLOWED_TAGS:
            attr_str = ""
            for name, value in attrs:
                if tag == "a" and name == "href":
                    attr_str = f' href="{value}"'
                    break
            self._result.append(f"<{tag}{attr_str}>")
            self._open_tags.append(tag)
        elif tag == "br":
            self._result.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _ALLOWED_TAGS:
            # Close any tags opened after this one (handles overlapping tags)
            while self._open_tags and self._open_tags[-1] != tag:
                self._result.append(f"</{self._open_tags.pop()}>")
            if self._open_tags and self._open_tags[-1] == tag:
                self._result.append(f"</{tag}>")
                self._open_tags.pop()

    def handle_data(self, data: str) -> None:
        self._result.append(data)

    def handle_entityref(self, name: str) -> None:
        self._result.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._result.append(f"&#{name};")

    def get_result(self) -> str:
        # Auto-close any remaining open tags
        for tag in reversed(self._open_tags):
            self._result.append(f"</{tag}>")
        return "".join(self._result)


def _sanitize_telegram_html(raw: str) -> str:
    parser = _TelegramHTMLSanitizer()
    parser.feed(raw)
    return parser.get_result()

# Cache for FAQ text loaded from FAQ_TEXT_URL; keys are language codes or "default"
_faq_cache: dict[str, str] = {}


def clear_faq_cache() -> None:
    _faq_cache.clear()


async def load_faq_text(language: str, url: str, proxy: str | None = None) -> None:
    """
    Fetch FAQ HTML from url and store in cache for the given language.
    Falls back silently on error.

    :param language: Language code ("ru" or "en")
    :param url: URL to fetch FAQ from
    :param proxy: Optional proxy URL
    """
    if not url:
        return

    try:
        async with aiohttp.ClientSession() as session:
            kwargs = {"proxy": proxy} if proxy and not proxy.startswith("socks") else {}
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10), **kwargs) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    # If URL returns HTML, sanitize it; if plain text with TG tags, use as-is
                    content_type = resp.headers.get("Content-Type", "")
                    if "text/html" in content_type:
                        clean = _sanitize_telegram_html(text)
                    else:
                        clean = text
                    _faq_cache[language] = clean
                    logger.info("FAQ text loaded for %s from %s (%d chars)", language, url, len(clean))
                else:
                    logger.warning("FAQ URL for %s returned status %d", language, resp.status)
    except Exception as e:
        logger.warning("Failed to load FAQ text for %s from %s: %s", language, url, e)

# Add other languages and their corresponding codes as needed.
# You can also keep only one language by removing the line with the unwanted language.
SUPPORTED_LANGUAGES = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
}


class Text(metaclass=ABCMeta):
    """
    Abstract base class for handling text data in different languages.
    """

    def __init__(self, language_code: str) -> None:
        """
        Initializes the Text instance with the specified language code.

        :param language_code: The language code (e.g., "ru" or "en").
        """
        self.language_code = language_code if language_code in SUPPORTED_LANGUAGES.keys() else "en"

    @property
    @abstractmethod
    def data(self) -> dict:
        """
        Abstract property to be implemented by subclasses. Represents the language-specific text data.

        :return: Dictionary containing language-specific text data.
        """
        raise NotImplementedError

    def get(self, code: str) -> str:
        """
        Retrieves the text corresponding to the provided code in the current language.

        :param code: The code associated with the desired text.
        :return: The text in the current language.
        """
        return self.data[self.language_code][code]


class TextMessage(Text):
    """
    Subclass of Text for managing text messages in different languages.
    """

    @property
    def data(self) -> dict:
        """
        Provides language-specific text data for text messages.

        :return: Dictionary containing language-specific text data for text messages.
        """
        return {
            "en": {
                "select_language": f"👋 <b>Hello</b>, {hbold('{full_name}')}!\n\nSelect language:",
                "change_language": "<b>Select language:</b>",
                "main_menu": _faq_cache.get("en", "<b>Write your question</b>, and we will answer you as soon as possible:"),
                "message_sent": "<b>Message sent!</b> Expect a response.",
                "message_edited": (
                    "<b>The message was edited only in your chat.</b> "
                    "To send an edited message, send it as a new message."
                ),
                "source": (
                    "Source code available at "
                    "<a href=\"https://github.com/nessshon/support-bot\">GitHub</a>"
                ),
                "user_started_bot": (
                    f"User {hbold('{name}')} started the bot!\n\n"
                    "List of available commands:\n\n"
                    "• /ban\n"
                    "Block/Unblock user"
                    "<blockquote>Block the user if you do not want to receive messages from him.</blockquote>\n\n"
                    "• /silent\n"
                    "Activate/Deactivate silent mode"
                    "<blockquote>When silent mode is enabled, messages are not sent to the user.</blockquote>\n\n"
                    "• /information\n"
                    "User information"
                    "<blockquote>Receive a message with basic information about the user.</blockquote>"
                ),
                "user_restarted_bot": f"User {hbold('{name}')} restarted the bot!",
                "user_stopped_bot": f"User {hbold('{name}')} stopped the bot!",
                "user_blocked": "<b>User blocked!</b> Messages from the user are not accepted.",
                "user_unblocked": "<b>User unblocked!</b> Messages from the user are being accepted again.",
                "blocked_by_user": "<b>Message not sent!</b> The bot has been blocked by the user.",
                "user_information": (
                    "<b>ID:</b>\n"
                    "- <code>{id}</code>\n"
                    "<b>Name:</b>\n"
                    "- {full_name}\n"
                    "<b>Status:</b>\n"
                    "- {state}\n"
                    "<b>Username:</b>\n"
                    "- {username}\n"
                    "<b>Email:</b>\n"
                    "- {email}\n"
                    "<b>Blocked:</b>\n"
                    "- {is_banned}\n"
                    "<b>Registration date:</b>\n"
                    "- {created_at}\n"
                ),
                "message_not_sent": "<b>Message not sent!</b> An unexpected error occurred.",
                "message_sent_to_user": "<b>Message sent to user!</b>",
                "silent_mode_enabled": (
                    "<b>Silent mode activated!</b> Messages will not be delivered to the user."
                ),
                "silent_mode_disabled": (
                    "<b>Silent mode deactivated!</b> The user will receive all messages."
                ),
            },
            "ru": {
                "select_language": f"👋 <b>Привет</b>, {hbold('{full_name}')}!\n\nВыберите язык:",
                "change_language": "<b>Выберите язык:</b>",
                "main_menu": _faq_cache.get("ru", """<b>Напишите свой вопрос</b>, и мы ответим вам как можно скорее:"""),
                "message_sent": "<b>Сообщение отправлено!</b> Ожидайте ответа.",
                "message_edited": (
                    "<b>Сообщение отредактировано только в вашем чате.</b> "
                    "Чтобы отправить отредактированное сообщение, отправьте его как новое сообщение."
                ),
                "source": (
                    "Исходный код доступен на "
                    "<a href=\"https://github.com/nessshon/support-bot\">GitHub</a>"
                ),
                "user_started_bot": (
                    f"Пользователь {hbold('{name}')} запустил(а) бота!\n\n"
                    "Список доступных команд:\n\n"
                    "• /ban\n"
                    "Заблокировать/Разблокировать пользователя"
                    "<blockquote>Заблокируйте пользователя, если не хотите получать от него сообщения.</blockquote>\n\n"
                    "• /silent\n"
                    "Активировать/Деактивировать тихий режим"
                    "<blockquote>При включенном тихом режиме сообщения не отправляются пользователю.</blockquote>\n\n"
                    "• /information\n"
                    "Информация о пользователе"
                    "<blockquote>Получить сообщение с основной информацией о пользователе.</blockquote>"
                ),
                "user_restarted_bot": f"Пользователь {hbold('{name}')} перезапустил(а) бота!",
                "user_stopped_bot": f"Пользователь {hbold('{name}')} остановил(а) бота!",
                "user_blocked": "<b>Пользователь заблокирован!</b> Сообщения от пользователя не принимаются.",
                "user_unblocked": "<b>Пользователь разблокирован!</b> Сообщения от пользователя вновь принимаются.",
                "blocked_by_user": "<b>Сообщение не отправлено!</b> Бот был заблокирован пользователем.",
                "user_information": (
                    "<b>ID:</b>\n"
                    "- <code>{id}</code>\n"
                    "<b>Имя:</b>\n"
                    "- {full_name}\n"
                    "<b>Статус:</b>\n"
                    "- {state}\n"
                    "<b>Username:</b>\n"
                    "- {username}\n"
                    "<b>Email:</b>\n"
                    "- {email}\n"
                    "<b>Заблокирован:</b>\n"
                    "- {is_banned}\n"
                    "<b>Дата регистрации:</b>\n"
                    "- {created_at}\n"
                ),
                "message_not_sent": "<b>Сообщение не отправлено!</b> Произошла неожиданная ошибка.",
                "message_sent_to_user": "<b>Сообщение отправлено пользователю!</b>",
                "silent_mode_enabled": (
                    "<b>Тихий режим активирован!</b> Сообщения не будут доставлены пользователю."
                ),
                "silent_mode_disabled": (
                    "<b>Тихий режим деактивирован!</b> Пользователь будет получать все сообщения."
                ),
            },
        }
