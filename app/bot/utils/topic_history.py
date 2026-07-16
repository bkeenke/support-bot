import html
import time
from datetime import datetime, timezone, timedelta

from aiogram.types import Message

from .redis import RedisStorage

# Telegram message limit is 4096; leave headroom for the header line.
_CHUNK_LIMIT = 3800
# Do not flood the topic with more than this many chunks per /show_old_messages call.
_MAX_CHUNKS = 10

_TZ = timezone(timedelta(hours=3))

_MEDIA_LABELS = {
    "photo": "📷 фото",
    "video": "🎬 видео",
    "video_note": "🎬 видеосообщение",
    "audio": "🎵 аудио",
    "voice": "🎤 голосовое",
    "document": "📎 документ",
    "sticker": "🩵 стикер",
    "other": "📦 вложение",
}


def describe_message(message: Message, from_: str) -> dict:
    """
    Build a compact history entry for a message.

    :param message: The message to describe.
    :param from_: "user" or "support".
    """
    entry: dict = {"ts": int(time.time()), "from": from_}

    if message.text:
        entry["type"] = "text"
        entry["text"] = message.text
        return entry

    if message.caption:
        entry["text"] = message.caption

    if message.photo:
        entry["type"] = "photo"
    elif message.video:
        entry["type"] = "video"
    elif message.video_note:
        entry["type"] = "video_note"
    elif message.audio:
        entry["type"] = "audio"
    elif message.voice:
        entry["type"] = "voice"
    elif message.document:
        entry["type"] = "document"
        if message.document.file_name:
            entry["file_name"] = message.document.file_name
    elif message.sticker:
        entry["type"] = "sticker"
    else:
        entry["type"] = "other"

    return entry


async def log_message(
    redis: RedisStorage,
    user_id: int,
    message: Message,
    from_: str,
) -> None:
    """Store a message in the user's history and bump their last activity."""
    entry = describe_message(message, from_)
    await redis.push_history(user_id, entry)
    await redis.set_last_activity(user_id, entry["ts"])


def _format_entry(entry: dict) -> str:
    ts = entry.get("ts")
    when = datetime.fromtimestamp(ts, _TZ).strftime("%d.%m.%Y %H:%M") if ts else "—"
    who = "👤" if entry.get("from") == "user" else "🛟"

    parts = []
    type_ = entry.get("type", "text")
    if type_ != "text":
        label = _MEDIA_LABELS.get(type_, _MEDIA_LABELS["other"])
        file_name = entry.get("file_name")
        parts.append(f"[{label}: {html.escape(file_name)}]" if file_name else f"[{label}]")
    if entry.get("text"):
        parts.append(html.escape(entry["text"]))

    body = " ".join(parts) if parts else "[пустое сообщение]"
    return f"<b>{when} {who}</b>\n{body}"


def format_history(entries: list[dict]) -> tuple[list[str], int]:
    """
    Format history entries into message chunks (newest last), capped at
    _MAX_CHUNKS. Returns (chunks, shown_count); shown_count < len(entries)
    means the oldest messages were truncated.
    """
    # Build chunks from the end so that when truncating we keep the latest messages.
    chunks: list[list[str]] = [[]]
    sizes = [0]
    shown = 0

    for entry in reversed(entries):
        line = _format_entry(entry)
        if sizes[-1] and sizes[-1] + len(line) + 2 > _CHUNK_LIMIT:
            if len(chunks) >= _MAX_CHUNKS:
                break
            chunks.append([])
            sizes.append(0)
        chunks[-1].insert(0, line)
        sizes[-1] += len(line) + 2
        shown += 1

    chunks.reverse()
    return ["\n\n".join(chunk) for chunk in chunks if chunk], shown
