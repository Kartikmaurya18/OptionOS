import logging
from typing import AsyncIterator, Optional

import orjson
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisPublisher:
    """Publishes every message to two places, because the two consumers
    downstream want different delivery semantics:

    - Pub/Sub (`channel`): ephemeral, fire-and-forget, delivered to *every*
      currently-subscribed process. This is what the WebSocket Gateway
      uses -- each gateway instance needs every tick, and a gateway that's
      down or restarting simply misses ticks until it's back (fine, since
      a fresh snapshot on reconnect catches any client up).
    - Streams (`stream_key`, if set): durable and consumer-group based.
      TickPersistenceService reads from this instead -- it needs
      at-least-once delivery (nothing silently lost if it's briefly down)
      and, when scaled to multiple replicas, work split across them rather
      than every replica getting every message.

    Used by the Market Data Service so it never has to know how many
    WebSocket Gateway instances or TickPersistenceService replicas exist --
    that's the whole point of putting a bus between ingestion and fan-out.
    """

    def __init__(
        self,
        redis_url: str,
        channel: str,
        stream_key: Optional[str] = None,
        stream_maxlen: int = 200_000,
    ) -> None:
        self._redis_url = redis_url
        self.channel = channel
        self.stream_key = stream_key
        self.stream_maxlen = stream_maxlen
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        self._client = redis.from_url(self._redis_url)
        await self._client.ping()
        logger.info(
            "RedisPublisher connected: %s (channel=%s, stream=%s)", self._redis_url, self.channel, self.stream_key
        )

    async def publish(self, message: dict) -> None:
        if self._client is None:
            raise RuntimeError("RedisPublisher.publish() called before connect()")
        payload = orjson.dumps(message)
        await self._client.publish(self.channel, payload)
        if self.stream_key:
            # maxlen caps the stream at ~stream_maxlen entries (approximate
            # trimming is cheaper than exact) so a persistence outage can't
            # grow Redis memory unbounded -- it bounds replay depth, not
            # correctness of the live path, which never reads the stream.
            await self._client.xadd(self.stream_key, {"data": payload}, maxlen=self.stream_maxlen, approximate=True)

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


class RedisStreamConsumer:
    """Durable, consumer-group based reader for the persistence path --
    distinct from RedisSubscriber's Pub/Sub above. Delivery is
    at-least-once: a crashed consumer's unacked entries get redelivered to
    whichever consumer in the group picks them up next, which is why
    TickPersistenceService's writes need to tolerate duplicates (see
    ClickHouseStore's ReplacingMergeTree for candles).
    """

    def __init__(self, redis_url: str, stream_key: str, group: str, consumer_name: str) -> None:
        self._redis_url = redis_url
        self.stream_key = stream_key
        self.group = group
        self.consumer_name = consumer_name
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        self._client = redis.from_url(self._redis_url)
        await self._client.ping()
        try:
            # id="0" (not "$") so a brand-new consumer group starts from the
            # beginning of whatever's currently in the stream, rather than
            # only messages published after the group was created.
            await self._client.xgroup_create(self.stream_key, self.group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise  # group already exists from a previous run -- not an error
        logger.info(
            "RedisStreamConsumer connected: %s (stream=%s, group=%s, consumer=%s)",
            self._redis_url,
            self.stream_key,
            self.group,
            self.consumer_name,
        )

    async def read_batch(self, count: int = 500, block_ms: int = 2000) -> list[tuple[str, dict]]:
        """Blocks up to block_ms waiting for new entries, then returns up to
        `count` (stream_id, message) pairs. Caller must ack() once a batch
        is durably written -- unacked entries stay pending and get
        redelivered."""
        if self._client is None:
            raise RuntimeError("RedisStreamConsumer.read_batch() called before connect()")
        response = await self._client.xreadgroup(
            self.group, self.consumer_name, {self.stream_key: ">"}, count=count, block=block_ms
        )
        batch: list[tuple[str, dict]] = []
        for _stream_key, entries in response:
            for entry_id, fields in entries:
                try:
                    batch.append((entry_id, orjson.loads(fields[b"data"])))
                except (orjson.JSONDecodeError, KeyError):
                    logger.warning("Dropped malformed stream entry %s", entry_id)
        return batch

    async def ack(self, entry_ids: list[str]) -> None:
        if entry_ids and self._client is not None:
            await self._client.xack(self.stream_key, self.group, *entry_ids)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
