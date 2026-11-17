from contextlib import asynccontextmanager

from redis.asyncio import Redis

MESSAGE_TTL = 60 * 60 * 24
REGISTRATION_TTL = 300  # seconds the bot waits for a GitLab ID


class Cache:
    """Remembers which Telegram message belongs to a merge request / pipeline."""

    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def _key(key: str) -> str:
        return f"tg:msg:{key}"

    async def get_message_id(self, key: str) -> int | None:
        value = await self.redis.get(self._key(key))
        return int(value) if value is not None else None

    async def set_message_id(self, key: str, message_id: int, ttl: int = MESSAGE_TTL) -> None:
        await self.redis.set(self._key(key), message_id, ex=ttl)

    async def delete_message_id(self, key: str) -> None:
        await self.redis.delete(self._key(key))

    async def start_registration(self, telegram_id: int) -> None:
        await self.redis.set(f"tg:registering:{telegram_id}", 1, ex=REGISTRATION_TTL)

    async def is_registering(self, telegram_id: int) -> bool:
        return bool(await self.redis.exists(f"tg:registering:{telegram_id}"))

    async def clear_registration(self, telegram_id: int) -> None:
        await self.redis.delete(f"tg:registering:{telegram_id}")

    # ---- state of one message (see services/flow.py) ----

    async def get_flow(self, key: str) -> str | None:
        return await self.redis.get(f"tg:flow:{key}")

    async def set_flow(self, key: str, raw: str, ttl: int = MESSAGE_TTL) -> None:
        await self.redis.set(f"tg:flow:{key}", raw, ex=ttl)

    async def delete_flow(self, key: str) -> None:
        await self.redis.delete(f"tg:flow:{key}")

    @asynccontextmanager
    async def lock(self, key: str):
        """Serializes events of one MR/pipeline, GitLab sends them almost simultaneously."""
        async with self.redis.lock(f"tg:lock:{key}", timeout=15, blocking_timeout=15):
            yield
