import logging
from typing import AsyncIterator, Optional

import orjson
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisPublisher:
    """Publishes ticks onto a Redis Pub/Sub channel.

    Used by the Market Data Service so it never has to know how many
    WebSocket Gateway instances (or other subscribers) exist -- that's the
    whole point of putting a bus between ingestion and fan-out.
    """

    def __init__(self, redis_url: str, channel: str) -> None:
        self._redis_url = redis_url
        self.channel = channel
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        self._client = redis.from_url(self._redis_url)
        await self._client.ping()
        logger.info("RedisPublisher connected: %s (channel=%s)", self._redis_url, self.channel)

    async def publish(self, message: dict) -> None:
        if self._client is None:
            raise RuntimeError("RedisPublisher.publish() called before connect()")
        await self._client.publish(self.channel, orjson.dumps(message))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()


class RedisSubscriber:
    """Subscribes to a Redis Pub/Sub channel and yields decoded messages.

    Used by the WebSocket Gateway -- every gateway instance subscribes
    independently and Redis fans the same message out to all of them, which
    is exactly the "any gateway pod can serve any client" property
    horizontal scaling needs.
    """

    def __init__(self, redis_url: str, channel: str) -> None:
        self._redis_url = redis_url
        self.channel = channel
        self._client: Optional[redis.Redis] = None
        self._pubsub = None

    async def connect(self) -> None:
        self._client = redis.from_url(self._redis_url)
        await self._client.ping()
        self._pubsub = self._client.pubsub()
        await self._pubsub.subscribe(self.channel)
        logger.info("RedisSubscriber connected: %s (channel=%s)", self._redis_url, self.channel)

    async def listen(self) -> AsyncIterator[dict]:
        if self._pubsub is None:
            raise RuntimeError("RedisSubscriber.listen() called before connect()")
        async for raw in self._pubsub.listen():
            if raw.get("type") != "message":
                continue  # ignore subscribe/unsubscribe confirmation events
            try:
                yield orjson.loads(raw["data"])
            except orjson.JSONDecodeError:
                logger.warning("Dropped malformed Redis pub/sub payload")
                continue

    async def close(self) -> None:
        if self._pubsub is not None:
            await self._pubsub.close()
        if self._client is not None:
            await self._client.aclose()
