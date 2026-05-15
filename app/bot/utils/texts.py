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


async def load_faq_text(url: str, proxy: str | None = None) -> None:
    """Fetch FAQ HTML from url and store in cache. Falls back silently on error."""
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
                    _faq_cache["ru"] = clean
                    _faq_cache["en"] = clean
                    logger.info("FAQ text loaded from %s (%d chars)", url, len(clean))
                else:
                    logger.warning("FAQ URL returned status %d, using fallback", resp.status)
    except Exception as e:
        logger.warning("Failed to load FAQ text from %s: %s", url, e)

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
                "main_menu": _faq_cache.get("ru", """<b>Ответы на частые вопросы 🔔</b>

🤔 Перед обращением в поддержку, пожалуйста, убедитесь, что вы используете сервис <b>VPN PPL</b>.
Бесплатно попробовать VPN PPL можно через нашего бота:
<a href="https://t.me/VPNPPLBot">https://t.me/VPNPPLBot</a>

❗️❗️❗️ Если вы не нашли ответ на свой вопрос ниже и ошибка связана с мобильным устройством, укажите в обращении ваш логин и приложите скриншот главного экрана приложения <b>Happ</b> или <b>Happ</b>, после чего отправьте его нам.
Это поможет нам понять, в чём может быть проблема, и быстрее вам помочь. ❗️❗️❗️

⸻

<b>Q. Как подключить другие устройства?</b>
<b>A.</b> Если на втором устройстве у вас тот же профиль Telegram, просто зайдите в нашего бота и нажмите кнопку <b>«Подключить VPN»</b>.

Если на втором устройстве используется другой профиль Telegram — ничего страшного.
Вы можете скопировать ваш VPN-ключ (ссылку) с текущего устройства и вставить его вручную в приложение <b>Happ</b> на втором устройстве.

<b>Чтобы найти свой ключ:</b>
В боте нажмите <b>«Мои подписки» → выберите активную подписку → «Ручная настройка»</b>.

⸻

<b>Q. Сколько устройств можно подключить на одну подписку?</b>
<b>A.</b>
• На обычном тарифе доступно подключение до 3 устройств.
• На 🏆 VIP-тарифе доступно подключение до 10 устройств.

⸻

<b>Q. У вас есть лимит трафика?</b>
<b>A.</b> Лимита нет. Если трафик подойдёт к концу, пожалуйста, сообщите нам — мы его обнулим.

⸻

<b>Q. Как активировать подписку на текущем или новом устройстве?</b>
<b>A.</b>
1. Зайдите в нашего бота.
2. Нажмите кнопку <b>«Подключить»</b>.
(Если вам нужно купить подписку, выберите <b>«Приобрести / продлить»</b> и оплатите её.)
3. Выберите нужное устройство.
4. Выполните шаги 1 и 2 из инструкции по настройке.

⸻

<b>Q. Как найти свой ключ / ссылку?</b>
<b>A.</b> Ваш ключ (ссылка) находится в нашем боте на текущем устройстве.

<b>Инструкция:</b>
1. Зайдите в бота <a href="https://t.me/VPNPPLBot">https://t.me/VPNPPLBot</a>.
2. Нажмите <b>«Мои подписки»</b>.
3. Выберите активную подписку.
4. Нажмите <b>«Ручная настройка»</b> — там будет ваш ключ (ссылка).

<b>После этого:</b>
• Откройте приложение <b>Happ</b>.
• Нажмите на значок «+».
• Вставьте ключ, выберите сервер (страну) и включите VPN.

⸻

<b>Q. Как активировать подписку на Android TV?</b>
<b>A.</b>
1. Включите Android TV или Android-приставку.
2. Откройте магазин приложений Google Play.
3. Скачайте приложение <b>Happ</b>, откройте его, нажмите <b>«Управление»</b>, затем <b>«Импорт с телефона»</b>.
4. На мобильном устройстве откройте <b>Happ</b>, нажмите на значок QR-кода рядом с выбранным сервером и отсканируйте код на экране ТВ.

⸻

<b>Q. Какие страны доступны?</b>
<b>A.</b>
• На обычном тарифе доступны серверы: Финляндия 🇫🇮, Нидерланды 🇳🇱, Польша 🇵🇱, Россия 🇷🇺.
• На 🏆 VIP-тарифе дополнительно доступен сервер США 🇺🇸.

⸻

<b>Q. Что делать, если VPN не работает на ПК?</b>
<b>A.</b> Проверьте, не установлены ли в браузере расширения для VPN или прокси, которыми вы пользовались ранее.
Они могут мешать стабильной работе нашего VPN.
К таким расширениям относятся любые инструменты для обхода блокировок (в том числе для доступа к рутрекеру и другим сайтам).

Также:
- Запустите <b>v2Ray</b> от имени администратора.
- В приложении откройте <b>Настройки → Настройки трафика → Режим</b> и выберите <b>«Туннель»</b>."""),
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
