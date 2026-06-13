from dataclasses import dataclass, field

from environs import Env


@dataclass
class ApiConfig:
    HOST: str
    PORT: int
    CORS_ORIGINS: list[str]
    GET_ID_URL: str | None
    GET_DATA_URL: str | None
    READ_WEBHOOK_URL: str | None
    READ_WEBHOOK_DELAY: int
    API_SECRET_KEY: str | None


@dataclass
class BotConfig:
    """
    Data class representing the configuration for the bot.

    Attributes:
    - TOKEN (str): The bot token.
    - DEV_ID (int): The developer's user ID.
    - DEV_IDS (list[int]): Additional developer user IDs.
    - GROUP_ID (int): The group chat ID.
    - BOT_EMOJI_ID (str): The custom emoji ID for the group's topic.
    - SHM_API_URL (str): Base URL for SHM user info page.
    """
    TOKEN: str
    DEV_ID: int
    DEV_IDS: list[int]
    GROUP_ID: int
    BOT_EMOJI_ID: str
    SHM_API_URL: str


@dataclass
class RedisConfig:
    """
    Data class representing the configuration for Redis.

    Attributes:
    - HOST (str): The Redis host.
    - PORT (int): The Redis port.
    - DB (int): The Redis database number.
    """
    HOST: str
    PORT: int
    DB: int

    def dsn(self) -> str:
        """
        Generates a Redis connection DSN (Data Source Name) using the provided host, port, and database.

        :return: The generated DSN.
        """
        return f"redis://{self.HOST}:{self.PORT}/{self.DB}"


@dataclass
class Config:
    """
    Data class representing the overall configuration for the application.

    Attributes:
    - bot (BotConfig): The bot configuration.
    - redis (RedisConfig): The Redis configuration.
    - api (ApiConfig): The widget HTTP API configuration.
    - proxy (str | None): Optional SOCKS5/HTTP proxy URL.
    - faq_ru_url (str | None): Optional URL to fetch FAQ HTML text in Russian.
    - faq_en_url (str | None): Optional URL to fetch FAQ HTML text in English.
    """
    bot: BotConfig
    redis: RedisConfig
    api: ApiConfig
    proxy: str | None
    faq_ru_url: str | None
    faq_en_url: str | None


def load_config() -> Config:
    """
    Load the configuration from environment variables and return a Config object.

    :return: The Config object with loaded configuration.
    """
    env = Env()
    env.read_env()

    return Config(
        bot=BotConfig(
            TOKEN=env.str("BOT_TOKEN"),
            DEV_ID=env.int("BOT_DEV_ID"),
            DEV_IDS=env.list("BOT_DEV_IDS", subcast=int, default=[]),
            GROUP_ID=env.int("BOT_GROUP_ID"),
            BOT_EMOJI_ID=env.str("BOT_EMOJI_ID"),
            SHM_API_URL=env.str("SHM_API_URL", default=""),
        ),
        redis=RedisConfig(
            HOST=env.str("REDIS_HOST"),
            PORT=env.int("REDIS_PORT"),
            DB=env.int("REDIS_DB"),
        ),
        api=ApiConfig(
            HOST=env.str("WIDGET_API_HOST", default="0.0.0.0"),
            PORT=env.int("WIDGET_API_PORT", default=8080),
            CORS_ORIGINS=[o for o in env.list("WIDGET_CORS_ORIGINS", default=[]) if o.strip()],
            GET_ID_URL=env.str("GET_ID_URL", default=None) or None,
            GET_DATA_URL=env.str("GET_DATA_URL", default=None) or None,
            READ_WEBHOOK_URL=env.str("READ_WEBHOOK_URL", default=None) or None,
            READ_WEBHOOK_DELAY=env.int("READ_WEBHOOK_DELAY", default=30),
            API_SECRET_KEY=env.str("API_SECRET_KEY", default=None) or None,
        ),
        proxy=env.str("PROXY_URL", default=None) or None,
        faq_ru_url=env.str("FAQ_TEXT_URL", default=None) or None,
        faq_en_url=env.str("FAQ_EN_TEXT_URL", default=None) or None,
    )
