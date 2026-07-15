import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
}


@dataclass(slots=True)
class Candle:
    time: int  # epoch ms, start of the bucket
    open: float
    high: float
    low: float
    close: float
    tick_count: int  # ticks observed in this bucket; 0 means carried-forward/flat

    @staticmethod
    def open_at(bucket_start: int, price: float) -> "Candle":
        return Candle(time=bucket_start, open=price, high=price, low=price, close=price, tick_count=1)

    @staticmethod
    def flat_at(bucket_start: int, price: float) -> "Candle":
        return Candle(time=bucket_start, open=price, high=price, low=price, close=price, tick_count=0)

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "tickCount": self.tick_count,
        }


def bucket_start_ms(ts_ms: float, bucket_ms: int) -> int:
    """Floors a timestamp to the start of its bucket, aligned to clock time
    -- mirrors frontend/src/lib/candleBuilder.ts's bucketStart()."""
    return int(ts_ms // bucket_ms) * bucket_ms


CandleKey = tuple[str, str]  # (instrument key, timeframe)
CandleListener = Callable[[str, str, Candle], None]


class CandleEngine:
    """Maintains one mutable active candle per (instrument, timeframe) and
    updates it in O(1) per tick.

    This replaces the frontend's lib/candleBuilder.ts, which recomputes OHLC
    buckets over the *entire* tick history on every call (cached only when
    nothing changed). That's fine for one strike's chart; it doesn't scale
    to a server computing candles for thousands of instruments on every
    tick. Here, a tick only ever touches the one active Candle object it
    belongs to -- no array rebuild, no re-sort, no allocation beyond the
    occasional new bucket.

    Silent buckets (no ticks at all) are handled by the same "catch up"
    mechanism whether they're discovered by a late real tick or by the
    background bucket-closer timer: the active candle is rolled forward
    bucket-by-bucket, emitting a flat carried-forward candle for each empty
    one, so the series is always gap-free regardless of how long an
    instrument stays quiet.
    """

    def __init__(self, timeframes: Optional[dict[str, int]] = None) -> None:
        self.timeframes = timeframes or TIMEFRAME_MS
        self._active: dict[CandleKey, Candle] = {}
        self._on_close: list[CandleListener] = []

    def on_close(self, listener: CandleListener) -> None:
        """Registered callbacks fire whenever a bucket rolls over (a candle
        closes) -- this is the broadcast/persistence hook (Part 2's
        TickPersistenceService and the WS gateway both subscribe here)."""
        self._on_close.append(listener)

    def get_active(self, key: str, timeframe: str) -> Optional[Candle]:
        return self._active.get((key, timeframe))

    def active_count(self) -> int:
        """How many (instrument, timeframe) candles are currently held in
        memory -- a memory footprint proxy, exported as a metric."""
        return len(self._active)

    def on_tick(self, key: str, price: float, ts_ms: float) -> None:
        for timeframe, bucket_ms in self.timeframes.items():
            self._apply(key, timeframe, bucket_ms, price, ts_ms)

    def _apply(self, key: str, timeframe: str, bucket_ms: int, price: float, ts_ms: float) -> None:
        bucket_start = bucket_start_ms(ts_ms, bucket_ms)
        candle_key = (key, timeframe)
        candle = self._active.get(candle_key)

        if candle is None:
            self._active[candle_key] = Candle.open_at(bucket_start, price)
            return

        if bucket_start < candle.time:
            return  # out-of-order/late tick for an already-closed bucket -- drop

        if bucket_start > candle.time:
            self._catch_up(key, timeframe, bucket_ms, bucket_start)
            candle = self._active[candle_key]
            # candle.time == bucket_start now, either freshly opened (if this
            # was the very first tick ever) or flat-carried by catch-up;
            # either way it's correct to apply this tick as an update below.

        if price > candle.high:
            candle.high = price
        if price < candle.low:
            candle.low = price
        candle.close = price
        candle.tick_count += 1

    def _catch_up(self, key: str, timeframe: str, bucket_ms: int, up_to_bucket_start: int) -> None:
        """Rolls the active candle forward bucket-by-bucket until its time
        reaches up_to_bucket_start, emitting (closing) each bucket passed
        through -- with a flat, carried-forward candle for any bucket that
        had no real ticks."""
        candle_key = (key, timeframe)
        candle = self._active[candle_key]
        while candle.time < up_to_bucket_start:
            next_start = candle.time + bucket_ms
            self._emit(key, timeframe, candle)
            candle = Candle.flat_at(next_start, candle.close)
            self._active[candle_key] = candle

    def _emit(self, key: str, timeframe: str, candle: Candle) -> None:
        for listener in self._on_close:
            listener(key, timeframe, candle)

    async def run_bucket_closer(self, timeframe: str) -> None:
        """Background task, one per active timeframe (not per instrument):
        sleeps until the next bucket boundary, then catches up every
        instrument tracked at this timeframe to that boundary -- closing
        buckets on a wall-clock schedule instead of waiting for whichever
        tick happens to arrive next."""
        bucket_ms = self.timeframes[timeframe]
        while True:
            now_ms = time.time() * 1000
            next_boundary = (int(now_ms // bucket_ms) + 1) * bucket_ms
            await asyncio.sleep(max(0.0, (next_boundary - now_ms) / 1000))
            keys = [k for (k, tf) in self._active if tf == timeframe]
            for key in keys:
                self._catch_up(key, timeframe, bucket_ms, next_boundary)
