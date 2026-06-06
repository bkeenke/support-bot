import asyncio
import json
import logging
import time
from pathlib import Path
from uuid import uuid4

import aiohttp
from aiohttp import web
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile

from app.bot.utils.create_forum_topic import create_forum_topic
from app.bot.utils.redis import RedisStorage
from app.bot.utils.redis.models import WebSession
from app.config import Config

_STATIC = Path(__file__).parent / 'static'

logger = logging.getLogger(__name__)
router = web.RouteTableDef()

MAX_TEXT_LEN = 4096
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
RATE_MESSAGES_PER_SESSION = (20, 60)  # 20 messages per session per minute
RATE_UPLOADS_PER_SESSION = (10, 60)   # 10 uploads per session per minute


def _cors(request: web.Request) -> dict:
    config: Config = request.app["config"]
    origin = request.headers.get("Origin", "")
    if not config.api.CORS_ORIGINS:
        allowed = "*"
    else:
        allowed = ""
        for domain in config.api.CORS_ORIGINS:
            domain = domain.strip()
            if not domain:
                continue
            if "://" in domain:
                match = origin == domain
            else:
                match = origin in (f"https://{domain}", f"http://{domain}")
            if match:
                allowed = origin
                break
    h = {
        "Access-Control-Allow-Headers": "Content-Type, X-Session-Id",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Vary": "Origin",
    }
    if allowed:
        h["Access-Control-Allow-Origin"] = allowed
    return h


def _json(data: dict, status: int = 200, request: web.Request = None) -> web.Response:
    return web.Response(
        text=json.dumps(data),
        status=status,
        content_type="application/json",
        headers=_cors(request) if request else {},
    )


async def _user_exists(http, url: str, user_id: int) -> bool:
    try:
        async with http.get(f"{url}?user_id={user_id}") as r:
            return r.status == 200
    except Exception:
        logger.warning("GET_ID_URL check failed for user_id=%s, allowing through", user_id)
        return True  # fail open: не блокируем при недоступности API


async def _fetch_user_data(http, url: str, user_id: int) -> dict:
    try:
        async with http.get(f"{url}?user_id={user_id}") as r:
            if r.status == 200:
                return await r.json()
    except Exception:
        logger.warning("GET_DATA_URL fetch failed for user_id=%s", user_id)
    return {}


async def _rate_exceeded(redis, key: str, limit: int, window: int) -> bool:
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    return count > limit


async def _get_session(request: web.Request) -> tuple["WebSession | None", "web.Response | None"]:
    sid = request.headers.get("X-Session-Id", "").strip()
    if not sid:
        return None, _json({"error": "Missing X-Session-Id"}, 401, request)
    rs: RedisStorage = request.app["rs"]
    session = await rs.get_web_session(sid)
    if not session:
        return None, _json({"error": "Invalid session"}, 401, request)
    return session, None


async def _ensure_topic(
    rs: RedisStorage,
    bot: Bot,
    config: Config,
    session: WebSession,
) -> tuple["int | None", "str | None"]:
    if session.thread_id:
        return session.thread_id, None

    # Guard against concurrent creation for the same session
    lock_key = f"web_topic_lock:{session.session_id}"
    acquired = await rs.redis.set(lock_key, "1", nx=True, ex=30)
    if not acquired:
        for _ in range(12):
            await asyncio.sleep(0.5)
            fresh = await rs.get_web_session(session.session_id)
            if fresh and fresh.thread_id:
                session.thread_id = fresh.thread_id
                return session.thread_id, None
        return None, "topic creation timeout"

    try:
        fresh = await rs.get_web_session(session.session_id)
        if fresh and fresh.thread_id:
            session.thread_id = fresh.thread_id
            return session.thread_id, None

        name = (
            f"User {session.external_id}"
            if session.type == "user"
            else f"Guest {session.external_id}"
        )
        thread_id = await create_forum_topic(bot, config, name)
        session.thread_id = thread_id
        await rs.update_web_session(session)
        return thread_id, None
    except Exception as exc:
        logger.exception("Failed to create web forum topic for session %s", session.session_id)
        return None, str(exc)
    finally:
        await rs.redis.delete(lock_key)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/widget.js")
async def serve_widget_js(request: web.Request) -> web.Response:
    return web.FileResponse(
        _STATIC / "widget.js",
        headers={
            "Content-Type": "application/javascript; charset=utf-8",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.options("/{tail:.*}")
async def preflight(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors(request))


@router.post("/widget/session")
async def create_session(request: web.Request) -> web.Response:
    rs: RedisStorage = request.app["rs"]
    config: Config = request.app["config"]

    try:
        body = await request.json()
    except Exception:
        return _json({"error": "Invalid JSON"}, 400, request)

    user_id: int | None = body.get("user_id")

    if not user_id:
        return _json({"error": "user_id required"}, 400, request)

    if config.api.GET_ID_URL:
        if not await _user_exists(request.app["http"], config.api.GET_ID_URL, int(user_id)):
            return _json({"error": "User not found"}, 404, request)

    existing = await rs.get_web_session_by_user_id(int(user_id))
    if existing:
        return _json({"session_id": existing.session_id, "is_new": False}, request=request)

    shm_data = {}
    if config.api.GET_DATA_URL:
        shm_data = await _fetch_user_data(request.app["http"], config.api.GET_DATA_URL, int(user_id))

    sid = str(uuid4())
    session = WebSession(
        session_id=sid,
        type="user",
        external_id=str(user_id),
        full_name=shm_data.get("full_name") or None,
        login=shm_data.get("login") or None,
    )
    await rs.create_web_session(session)
    return _json({"session_id": sid, "is_new": True}, request=request)


@router.post("/widget/message")
async def send_message(request: web.Request) -> web.Response:
    session, err = await _get_session(request)
    if err or session is None:
        return err or _json({"error": "Invalid session"}, 401, request)

    rs: RedisStorage = request.app["rs"]
    bot: Bot = request.app["bot"]
    config: Config = request.app["config"]

    if await _rate_exceeded(rs.redis, f"rl:sess:{session.session_id}:msg", *RATE_MESSAGES_PER_SESSION):
        return _json({"error": "Too many messages"}, 429, request)

    try:
        body = await request.json()
    except Exception:
        return _json({"error": "Invalid JSON"}, 400, request)

    text = (body.get("text") or "").strip()
    if not text:
        return _json({"error": "text required"}, 400, request)
    if len(text) > MAX_TEXT_LEN:
        return _json({"error": "Text too long"}, 400, request)

    for attempt in range(2):
        thread_id, err_msg = await _ensure_topic(rs, bot, config, session)
        if err_msg:
            return _json({"error": "Failed to create topic"}, 500, request)
        try:
            await bot.send_message(
                chat_id=config.bot.GROUP_ID,
                message_thread_id=thread_id,
                text=text,
            )
            await rs.push_web_inbox(session.session_id, {
                "ts": int(time.time()), "from": "user", "text": text,
            })
            break
        except TelegramBadRequest as exc:
            if "message thread not found" in str(exc).lower() and attempt == 0:
                logger.warning("Web topic deleted, resetting (session=%s)", session.session_id)
                session.thread_id = None
                await rs.update_web_session(session)
                continue
            logger.error("Telegram error sending web message: %s", exc)
            return _json({"error": "Telegram API error"}, 500, request)
        except TelegramAPIError as exc:
            logger.error("Telegram error sending web message: %s", exc)
            return _json({"error": "Telegram API error"}, 500, request)

    return _json({"ok": True}, request=request)


@router.post("/widget/upload")
async def upload_photo(request: web.Request) -> web.Response:
    session, err = await _get_session(request)
    if err or session is None:
        return err or _json({"error": "Invalid session"}, 401, request)

    rs: RedisStorage = request.app["rs"]
    bot: Bot = request.app["bot"]
    config: Config = request.app["config"]

    if await _rate_exceeded(rs.redis, f"rl:sess:{session.session_id}:upload", *RATE_UPLOADS_PER_SESSION):
        return _json({"error": "Too many uploads"}, 429, request)

    try:
        reader = await request.multipart()
        field = await reader.next()
    except Exception:
        return _json({"error": "Invalid multipart"}, 400, request)

    if not field or field.name != "file":
        return _json({"error": "field 'file' required"}, 400, request)

    data = await field.read(decode=True)
    if len(data) > MAX_FILE_BYTES:
        return _json({"error": "File too large (max 10 MB)"}, 400, request)

    filename = field.filename or "upload.jpg"

    for attempt in range(2):
        thread_id, err_msg = await _ensure_topic(rs, bot, config, session)
        if err_msg:
            return _json({"error": "Failed to create topic"}, 500, request)
        try:
            sent = await bot.send_photo(
                chat_id=config.bot.GROUP_ID,
                message_thread_id=thread_id,
                photo=BufferedInputFile(data, filename=filename),
            )
            assert sent.photo
            await rs.push_web_inbox(session.session_id, {
                "ts": int(time.time()), "from": "user",
                "photo_file_id": sent.photo[-1].file_id,
            })
            break
        except TelegramBadRequest as exc:
            if "message thread not found" in str(exc).lower() and attempt == 0:
                logger.warning("Web topic deleted, resetting (session=%s)", session.session_id)
                session.thread_id = None
                await rs.update_web_session(session)
                continue
            # Fallback: try as document (e.g. not a valid photo)
            try:
                sent = await bot.send_document(
                    chat_id=config.bot.GROUP_ID,
                    message_thread_id=thread_id,
                    document=BufferedInputFile(data, filename=filename),
                )
                assert sent.document
                await rs.push_web_inbox(session.session_id, {
                    "ts": int(time.time()), "from": "user",
                    "doc_file_id": sent.document.file_id,
                    "file_name": sent.document.file_name or filename,
                })
                break
            except TelegramAPIError as exc2:
                logger.error("Telegram error uploading web file: %s", exc2)
                return _json({"error": "Telegram API error"}, 500, request)
        except TelegramAPIError as exc:
            logger.error("Telegram error uploading web file: %s", exc)
            return _json({"error": "Telegram API error"}, 500, request)

    return _json({"ok": True}, request=request)


async def _get_tg_file_path(bot: Bot, redis, file_id: str) -> str | None:
    cache_key = f"tg_fp:{file_id}"
    cached = await redis.get(cache_key)
    if cached:
        return cached.decode()
    try:
        tg_file = await bot.get_file(file_id)
        await redis.setex(cache_key, 3600, tg_file.file_path)
        return tg_file.file_path
    except Exception as exc:
        logger.error("get_file failed for file_id=%s: %s", file_id, exc)
        return None


@router.get("/widget/file/{file_id}")
async def proxy_file(request: web.Request) -> web.StreamResponse:
    sid = request.rel_url.query.get("sid", "").strip()
    if not sid:
        return web.Response(status=401)

    rs: RedisStorage = request.app["rs"]
    if not await rs.get_web_session(sid):
        return web.Response(status=401)

    file_id = request.match_info["file_id"]
    bot: Bot = request.app["bot"]

    file_path = await _get_tg_file_path(bot, rs.redis, file_id)
    if not file_path:
        logger.error("proxy_file: no file_path for file_id=%.30s", file_id)
        return web.Response(status=404)

    url = f"https://api.telegram.org/file/bot{bot.token}/{file_path}"
    try:
        timeout = aiohttp.ClientTimeout(total=120, connect=10)
        async with request.app["http"].get(url, timeout=timeout) as r:
            if r.status != 200:
                logger.error("proxy_file: telegram returned %s for %s", r.status, file_path)
                return web.Response(status=404)
            content_type = r.headers.get("Content-Type", "application/octet-stream")
            response = web.StreamResponse(headers={
                "Content-Type": content_type,
                "Cache-Control": "private, max-age=3600",
            })
            await response.prepare(request)
            async for chunk in r.content.iter_chunked(64 * 1024):
                await response.write(chunk)
            await response.write_eof()
            return response
    except Exception as exc:
        logger.error("proxy_file: download failed for %s: %s", file_path, exc)
        return web.Response(status=502)


@router.get("/widget/messages")
async def get_messages(request: web.Request) -> web.Response:
    session, err = await _get_session(request)
    if err or session is None:
        return err or _json({"error": "Invalid session"}, 401, request)

    rs: RedisStorage = request.app["rs"]

    try:
        offset = max(0, int(request.rel_url.query.get("offset", 0)))
    except ValueError:
        offset = 0

    raw = await rs.get_web_inbox(session.session_id, offset)
    total = await rs.get_web_inbox_len(session.session_id)

    # Подменяем file_id на прокси-URL — токен бота клиент не видит
    sid = session.session_id
    messages = []
    for msg in raw:
        m = {k: v for k, v in msg.items() if k not in ("photo_file_id", "doc_file_id")}
        if "photo_file_id" in msg:
            m["photo_url"] = f"/widget/file/{msg['photo_file_id']}?sid={sid}"
        if "doc_file_id" in msg:
            m["file_url"] = f"/widget/file/{msg['doc_file_id']}?sid={sid}"
        messages.append(m)

    return _json({"messages": messages, "total": total, "offset": offset}, request=request)
