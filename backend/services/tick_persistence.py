import logging
from datetime import datetime, timezone

from observability.metrics import tick_persistence_batch_size, tick_persistence_write_errors_total
from services.clickhouse_store import ClickHouseStore
from services.message_bus import RedisStreamConsumer

logger = logging.getLogger(__name__)


class TickPersistenceService:
    """Consumes the durable Redis stream (never the ephemeral Pub/Sub
    channel -- see message_bus.py) and batches writes into ClickHouse.

    Entirely off the hot path: this can lag by hundreds of milliseconds, or
    even be down for a while, without affecting tick-to-paint latency for
    connected browsers, which go through Pub/Sub + WebSocketGateway instead.
    A batch is only ack'd after it's durably written, so a crash mid-batch
    just means Redis redelivers it on restart -- never silently drops it.
    """

    def __init__(
        self,
        consumer: RedisStreamConsumer,
        store: ClickHouseStore,
        batch_size: int = 500,
        block_ms: int = 2000,
    ) -> None:
        self.consumer = consumer
        self.store = store
        self.batch_size = batch_size
        self.block_ms = block_ms

    async def run_forever(self) -> None:
        await self.consumer.connect()
        while True:
            batch = await self.consumer.read_batch(count=self.batch_size, block_ms=self.block_ms)
            if not batch:
                continue  # xreadgroup timed out with nothing new -- just poll again
            await self._process_batch(batch)

    async def _process_batch(self, batch: list[tuple[str, dict]]) -> None:
        tick_rows: list[tuple] = []
        candle_rows: list[tuple] = []
        entry_ids: list[str] = []

        for entry_id, message in batch:
            entry_ids.append(entry_id)
            msg_type = message.get("type")

            if msg_type == "row_update":
                row = message.get("row", {})
                straddle = row.get("straddle")
                if straddle is not None:
                    tick_rows.append(
                        (
                            message["asset"],
                            row["strike"],
                            datetime.fromtimestamp(row["lastUpdated"], tz=timezone.utc),
                            straddle,
                        )
                    )
            elif msg_type == "candle_update":
                candle = message["candle"]
                candle_rows.append(
                    (
                        message["asset"],
                        message["strike"],
                        message["timeframe"],
                        datetime.fromtimestamp(candle["time"] / 1000, tz=timezone.utc),
                        candle["open"],
                        candle["high"],
                        candle["low"],
                        candle["close"],
                        candle["tickCount"],
                    )
                )
            # snapshot/spot_update/status: not persisted -- derived from live
            # state or transient, nothing a backfill query needs.

        try:
            await self.store.insert_ticks(tick_rows)
            await self.store.insert_candles(candle_rows)
        except Exception:
            tick_persistence_write_errors_total.inc()
            logger.exception("Failed to write batch to ClickHouse; leaving unacked for redelivery")
            return  # don't ack -- Redis will redeliver this batch to the group

        tick_persistence_batch_size.observe(len(entry_ids))
        await self.consumer.ack(entry_ids)
