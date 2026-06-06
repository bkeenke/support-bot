from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta


def _now_str() -> str:
    return datetime.now(timezone(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M:%S %Z")


@dataclass
class WebSession:
    """Represents a web widget chat session (anonymous guest or linked SHM user)."""
    session_id: str
    type: str           # "user" | "guest"
    external_id: str    # str(shm_user_id) or guest_id string
    thread_id: int | None = None
    full_name: str | None = None
    login: str | None = None
    created_at: str = field(default_factory=_now_str)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UserData:
    """Data class representing user information."""
    message_thread_id: int | None
    message_silent_id: int | None
    message_silent_mode: bool

    id: int
    full_name: str
    username: str | None
    state: str = "member"
    is_banned: bool = False
    language_code: str | None = None
    email: str | None = None
    created_at: str = field(default_factory=_now_str)

    def to_dict(self) -> dict:
        """
        Converts UserData object to a dictionary.

        :return: Dictionary representation of UserData.
        """
        return asdict(self)
