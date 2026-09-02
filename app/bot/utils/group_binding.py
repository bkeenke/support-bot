import logging

from app.config import Config
from .redis import RedisStorage

logger = logging.getLogger(__name__)


async def _scan(redis, match: str) -> list[bytes]:
    keys: list[bytes] = []
    async for key in redis.scan_iter(match=match, count=500):
        keys.append(key)
    return keys


async def ensure_group_binding(redis: RedisStorage, config: Config) -> bool:
    """
    Bind stored topic/thread IDs to the group they were created in.

    Forum thread IDs are only meaningful inside one chat. If BOT_GROUP_ID
    changes, every stored message_thread_id points at the old group, and
    reusing it against the new group is actively harmful: most IDs are
    invalid, but the ones that happen to collide with a real topic in the
    new group get reopened, written into, or deleted — i.e. one user's
    stale ID silently hijacks another user's live topic.

    On a group change (or the first run after this fence was introduced)
    all thread bindings are dropped so topics are recreated on demand.
    Message history (history:{user_id}) and web inboxes are untouched.

    :return: True if a purge was performed.
    """
    current = config.bot.GROUP_ID
    stored = await redis.get_bound_group_id()

    if stored == current:
        return False

    user_ids = await redis.get_all_users_ids()
    session_keys = await _scan(redis.redis, "web_session:*")

    if stored is None and not user_ids and not session_keys:
        # Fresh install — nothing to purge, just record the binding.
        await redis.set_bound_group_id(current)
        logger.info("Bound topic storage to group %s", current)
        return False

    logger.warning(
        "Group changed (%s -> %s): dropping stale forum topic bindings "
        "for %s user(s) and %s web session(s); message history is kept",
        stored if stored is not None else "unknown",
        current,
        len(user_ids),
        len(session_keys),
    )

    for user_id in user_ids:
        user_data = await redis.get_user(user_id)
        if user_data is None:
            continue
        if user_data.message_thread_id is None and user_data.message_silent_id is None:
            continue
        user_data.message_thread_id = None
        # Message IDs are per-chat too, so the pinned "silent mode" message
        # from the old group is meaningless here.
        user_data.message_silent_id = None
        await redis.update_user(user_id, user_data)

    for key in session_keys:
        session_id = (key.decode() if isinstance(key, bytes) else key).split(":", 1)[1]
        session = await redis.get_web_session(session_id)
        if session is None or session.thread_id is None:
            continue
        session.thread_id = None
        await redis.update_web_session(session)

    stale_patterns = (
        f"{redis.NAME}_thread:*",     # thread -> user index
        f"{redis.NAME}_index_*",      # legacy thread -> user index
        "topic_valid:*",              # cached "this topic exists" probes
        "web_thread:*",               # thread -> web session index
    )
    for pattern in stale_patterns:
        keys = await _scan(redis.redis, pattern)
        if keys:
            await redis.redis.delete(*keys)

    await redis.set_bound_group_id(current)
    logger.info("Topic storage rebound to group %s", current)
    return True
