import logging
from datetime import datetime, timezone
from typing import Optional

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from config import settings

logger = logging.getLogger(__name__)

CREATE_TICKS_TABLE = """
CREATE TABLE IF NOT EXISTS ticks (
    asset String,
    strike Float64,
    ts DateTime64(3),
    straddle Float64
) ENGINE = MergeTree
ORDER BY (asset, strike, ts)
TTL toDateTime(ts) + INTERVAL 30 DAY
"""

# ReplacingMergeTree (not plain MergeTree) because the Redis consumer group
# feeding this gives at-least-once delivery -- a crashed/restarted
# TickPersistenceService redelivers its last unacked batch, and without
# dedup that would insert the same closed candle twice. ORDER BY is the
# effective dedup key; FINAL at query time forces the dedup before backfill
# reads it (see query_candles below) -- acceptable cost since backfill reads
# are infrequent and latency-tolerant, unlike the live tick path.
CREATE_CANDLES_TABLE = """
CREATE TABLE IF NOT EXISTS candles (
    asset String,
    strike Float64,
    timeframe LowCardinality(String),
    bucket_start DateTime64(3),
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    tick_count UInt32
) ENGINE = ReplacingMergeTree
ORDER BY (asset, strike, timeframe, bucket_start)
TTL toDateTime(bucket_start) + INTERVAL 90 DAY
"""


class ClickHouseStore:
    """Durable tick + candle storage, and the read path for
    HistoricalBackfillService's /api/candles endpoint."""

    def __init__(self) -> None:
        self._client: Optional[AsyncClient] = None

    async def connect(self) -> None:
        self._client = await clickhouse_connect.get_async_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
        )
        await self._client.command(CREATE_TICKS_TABLE)
        await self._client.command(CREATE_CANDLES_TABLE)
        logger.info(
            "ClickHouseStore connected and schema ensured (%s:%s/%s)",
            settings.clickhouse_host,
            settings.clickhouse_port,
            settings.clickhouse_database,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def insert_ticks(self, rows: list[tuple[str, float, datetime, float]]) -> None:
        if not rows or self._client is None:
            return
        await self._client.insert("ticks", rows, column_names=["asset", "strike", "ts", "straddle"])

    async def insert_candles(self, rows: list[tuple]) -> None:
        if not rows or self._client is None:
            return
        await self._client.insert(
            "candles",
            rows,
            column_names=["asset", "strike", "timeframe", "bucket_start", "open", "high", "low", "close", "tick_count"],
        )

    async def query_candles(self, asset: str, strike: float, timeframe: str, start_ms: int, end_ms: int) -> list[dict]:
        """Closed candles for one instrument/timeframe in [start_ms, end_ms)
        (epoch ms), ordered oldest-first -- what a chart mount backfills
        with before switching over to the live WS feed for the same bucket
        alignment (see Part 5 of the architecture doc on why the boundary
        has to line up exactly)."""
        if self._client is None:
            return []
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
        result = await self._client.query(
            """
            SELECT bucket_start, open, high, low, close, tick_count
            FROM candles FINAL
            WHERE asset = {asset:String} AND strike = {strike:Float64} AND timeframe = {timeframe:String}
              AND bucket_start >= {start_dt:DateTime64(3)} AND bucket_start < {end_dt:DateTime64(3)}
            ORDER BY bucket_start ASC
            """,
            parameters={"asset": asset, "strike": strike, "timeframe": timeframe, "start_dt": start_dt, "end_dt": end_dt},
        )
        return [
            {
                "time": int(row[0].timestamp() * 1000),
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "tickCount": row[5],
            }
            for row in result.result_rows
        ]
