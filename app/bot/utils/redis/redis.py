import json

from redis.asyncio import Redis

from .models import UserData, WebSession


class RedisStorage:
    """Class for managing user data storage using Redis."""

    NAME = "users"

    def __init__(self, redis: Redis) -> None:
        """
        Initializes the RedisStorage instance.

        :param redis: The Redis instance to be used for data storage.
        """
        self.redis = redis

    async def _get(self, name: str, key: str | int) -> bytes | None:
        """
        Retrieves data from Redis.

        :param name: The name of the Redis hash.
        :param key: The key to be retrieved.
        :return: The retrieved data or None if not found.
        """
        async with self.redis.client() as client:
            return await client.hget(name, key)

    async def _set(self, name: str, key: str | int, value: any) -> None:
        """
        Sets data in Redis.

        :param name: The name of the Redis hash.
        :param key: The key to be set.
        :param value: The value to be set.
        """
        async with self.redis.client() as client:
            await client.hset(name, key, value)

    async def _update_index(self, message_thread_id: int, user_id: int) -> None:
        """
        Updates the user index in Redis.

        :param message_thread_id: The ID of the message thread.
        :param user_id: The ID of the user to be updated in the index.
        """
        index_key = f"{self.NAME}_index_{message_thread_id}"
        await self._set(index_key, user_id, "1")

    async def get_by_message_thread_id(self, message_thread_id: int) -> UserData | None:
        """
        Retrieves user data based on message thread ID.

        :param message_thread_id: The ID of the message thread.
        :return: The user data or None if not found.
        """
        user_id = await self._get_user_id_by_message_thread_id(message_thread_id)
        return None if user_id is None else await self.get_user(user_id)

    async def _get_user_id_by_message_thread_id(self, message_thread_id: int) -> int | None:
        """
        Retrieves user ID based on message thread ID.

        :param message_thread_id: The ID of the message thread.
        :return: The user ID or None if not found.
        """
        index_key = f"{self.NAME}_index_{message_thread_id}"
        async with self.redis.client() as client:
            user_ids = await client.hkeys(index_key)
            return int(user_ids[0]) if user_ids else None

    async def get_user(self, id_: int) -> UserData | None:
        """
        Retrieves user data based on user ID.

        :param id_: The ID of the user.
        :return: The user data or None if not found.
        """
        data = await self._get(self.NAME, id_)
        if data is not None:
            decoded_data = json.loads(data)
            return UserData(**decoded_data)
        return None

    async def update_user(self, id_: int, data: UserData) -> None:
        """
        Updates user data in Redis.

        :param id_: The ID of the user to be updated.
        :param data: The updated user data.
        """
        json_data = json.dumps(data.to_dict())
        await self._set(self.NAME, id_, json_data)
        await self._update_index(data.message_thread_id, id_)

    async def get_all_users_ids(self) -> list[int]:
        """
        Retrieves all user IDs stored in the Redis hash.

        :return: A list of all user IDs.
        """
        async with self.redis.client() as client:
            user_ids = await client.hkeys(self.NAME)
            return [int(user_id) for user_id in user_ids]

    # ------------------------------------------------------------------
    # Web widget session methods
    # ------------------------------------------------------------------

    async def get_web_session(self, session_id: str) -> WebSession | None:
        data = await self.redis.get(f"web_session:{session_id}")
        if data:
            return WebSession(**json.loads(data))
        return None

    async def get_web_session_by_user_id(self, user_id: int) -> WebSession | None:
        sid = await self.redis.get(f"web_user:{user_id}")
        return await self.get_web_session(sid.decode()) if sid else None

    async def get_web_session_by_guest_id(self, guest_id: str) -> WebSession | None:
        sid = await self.redis.get(f"web_guest:{guest_id}")
        return await self.get_web_session(sid.decode()) if sid else None

    async def create_web_session(self, session: WebSession) -> None:
        await self.redis.set(f"web_session:{session.session_id}", json.dumps(session.to_dict()))
        if session.type == "user":
            await self.redis.set(f"web_user:{session.external_id}", session.session_id)
        else:
            await self.redis.set(f"web_guest:{session.external_id}", session.session_id)

    async def update_web_session(self, session: WebSession) -> None:
        await self.redis.set(f"web_session:{session.session_id}", json.dumps(session.to_dict()))
        if session.thread_id:
            await self.redis.set(f"web_thread:{session.thread_id}", session.session_id)

    async def get_session_id_by_thread(self, thread_id: int) -> str | None:
        sid = await self.redis.get(f"web_thread:{thread_id}")
        return sid.decode() if sid else None

    async def push_web_inbox(self, session_id: str, message: dict) -> None:
        await self.redis.rpush(f"web_inbox:{session_id}", json.dumps(message))

    async def get_web_inbox(self, session_id: str, offset: int = 0) -> list[dict]:
        raw = await self.redis.lrange(f"web_inbox:{session_id}", offset, -1)
        return [json.loads(item) for item in raw]

    async def get_web_inbox_len(self, session_id: str) -> int:
        return await self.redis.llen(f"web_inbox:{session_id}")
