import asyncio
import logging
import time
from typing import Optional

import httpx
import orjson
import websockets
from websockets.exceptions import ConnectionClosed

from config import settings, spot_index_symbol
from schemas.ws_messages import (
    CandlePayload,
    CandleUpdateMessage,
    OptionRowPayload,
    RowUpdateMessage,
    SpotUpdateMessage,
    StatusMessage,
)
from observability.metrics import (
    candle_engine_active_keys,
    delta_reconnects_total,
    option_store_row_count,
    tick_to_publish_seconds,
    ticks_ingested_total,
)
from services.candle_engine import Candle, CandleEngine
from services.delta_rest import fetch_ticker_snapshot
from services.message_bus import RedisPublisher
from services.option_store import OptionStore
from services.symbol_resolver import SymbolResolver

logger = logging.getLogger(__name__)


class DeltaStreamStatus:
    """Live connection state surfaced to the frontend header bar, for one
    asset's shard."""

    def __init__(self, asset: str) -> None:
        self.asset = asset
        self.connected = False
        self.reconnect_attempts = 0
        self.last_message_time: Optional[float] = None
        self.expiry: Optional[str] = None
        self.strike_count = 0

    def to_dict(self) -> dict:
        return StatusMessage(
            asset=self.asset,
            connected=self.connected,
            reconnectAttempts=self.reconnect_attempts,
            lastMessageTime=self.last_message_time,
            expiry=self.expiry,
            strikeCount=self.strike_count,
        ).model_dump()



class DeltaOptionsStreamer:
    """Owns the upstream connection to Delta Exchange's public WebSocket for
    one asset (one shard -- see Part 1/Part 4 of the architecture doc: one
    instance of this class runs per configured asset, each with its own
    OptionStore and CandleEngine, so a reconnect storm on one asset's feed
    never touches another's).

    Resolves the nearest options expiry for this asset, subscribes to
    v2/ticker for every call/put symbol in that chain plus the spot index,
    keeps OptionStore updated, and publishes single-row diffs to Redis --
    tagged with `asset` -- for any number of WebSocket Gateway instances to
    pick up and filter (see websocket/redis_bridge.py and
    websocket/manager.py). This class has no idea how many gateways exist,
    or whether any browser tab is even watching. Runs forever, reconnecting
    with exponential backoff on any drop (network error, Delta restart,
    etc).
    """

    def __init__(self, asset: str, store: OptionStore, publisher: RedisPublisher) -> None:
        self.asset = asset
        self.store = store
        self.publisher = publisher
        self.status = DeltaStreamStatus(asset)
        self.resolver = SymbolResolver(underlying=asset)
        self.candles = CandleEngine()
        self.candles.on_close(self._on_candle_close)
        self._symbols: list[str] = []
        self._bucket_closer_tasks: list[asyncio.Task] = []
        self._expiry_watcher_task: Optional[asyncio.Task] = None
        self._active_ws: Optional[websockets.ClientConnection] = None

    def _on_candle_close(self, key: str, timeframe: str, candle: Candle) -> None:
        """CandleEngine callback -- fires synchronously whenever a bucket
        rolls over. Scheduled as a task rather than awaited in place since
        this runs inside CandleEngine's own call stack, not the WS loop."""
        message = CandleUpdateMessage(
            asset=self.asset,
            strike=float(key),
            timeframe=timeframe,
            candle=CandlePayload(**candle.to_dict()),
        ).model_dump()
        asyncio.create_task(self.publisher.publish(message))

    def _start_candle_bucket_closers(self) -> None:
        """One lightweight background task per timeframe (not per
        instrument) that closes silent buckets on a wall-clock schedule.
        Started once, on the first successful bootstrap."""
        if self._bucket_closer_tasks:
            return
        for timeframe in self.candles.timeframes:
            self._bucket_closer_tasks.append(asyncio.create_task(self.candles.run_bucket_closer(timeframe)))

    def _start_expiry_watcher(self, http_client: httpx.AsyncClient) -> None:
        """Background task, started once: periodically re-resolves the
        option chain so a contract rolling over to a new nearest expiry
        doesn't leave this shard silently subscribed to symbols that
        stopped trading (Delta simply stops sending ticks for an expired
        contract -- there's no error to react to, so this has to poll)."""
        if self._expiry_watcher_task is not None:
            return
        self._expiry_watcher_task = asyncio.create_task(self._watch_for_expiry_rollover(http_client))

    async def _watch_for_expiry_rollover(self, http_client: httpx.AsyncClient) -> None:
        while True:
            await asyncio.sleep(settings.expiry_refresh_interval)
            try:
                rolled_over = await self._refresh_chain(http_client)
            except Exception:
                logger.exception("%s: failed to check for expiry rollover", self.asset)
                continue
            if rolled_over and self._active_ws is not None:
                # Closing the live connection is what makes the new
                # self._symbols actually take effect: _connect_and_stream's
                # subscribe payload is only built at connect time, and
                # run_forever's outer loop reconnects immediately using the
                # values this method just updated.
                await self._active_ws.close()

    async def run_forever(self) -> None:
        delay = settings.ws_reconnect_min_delay
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            while True:
                try:
                    if self.status.expiry is None:
                        await self._bootstrap(http_client)
                        self._start_candle_bucket_closers()
                        self._start_expiry_watcher(http_client)

                    await self._connect_and_stream()
                    delay = settings.ws_reconnect_min_delay
                except (ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
                    logger.warning("Delta WebSocket disconnected: %s", exc)
                except Exception:
                    logger.exception("Unexpected error in Delta stream loop")

                self.status.connected = False
                self.status.reconnect_attempts += 1
                delta_reconnects_total.labels(asset=self.asset).inc()
                await self.publisher.publish(self.status.to_dict())
                await asyncio.sleep(delay)
                delay = min(delay * 2, settings.ws_reconnect_max_delay)

    async def _bootstrap(self, http_client: httpx.AsyncClient) -> None:
        """First-time setup: resolve the nearest expiry via SymbolResolver
        and seed the store with a REST snapshot before streaming."""
        await self._refresh_chain(http_client)

    async def _refresh_chain(self, http_client: httpx.AsyncClient) -> bool:
        """Resolves the current nearest expiry and, if it differs from what
        this shard already has (first call, or a rollover), registers every
        strike and reseeds via REST. Returns True if the chain actually
        changed, so callers know whether a resubscribe is needed."""
        index = await self.resolver.resolve(http_client)
        if index.expiry == self.status.expiry:
            return False

        if self.status.expiry is not None:
            logger.info("%s: expiry rolled over %s -> %s", self.asset, self.status.expiry, index.expiry)

        self.status.expiry = index.expiry
        for strike in index.strikes:
            self.store.ensure_row(
                strike,
                index.call_symbol_by_strike.get(strike, ""),
                index.put_symbol_by_strike.get(strike, ""),
            )
        self._symbols = index.all_symbols
        self.status.strike_count = self.store.row_count()
        option_store_row_count.labels(asset=self.asset).set(self.status.strike_count)

        try:
            tickers = await fetch_ticker_snapshot(http_client, self.asset, self._symbols)
            for ticker in tickers:
                self._apply_ticker(ticker, broadcast=False)
        except Exception:
            logger.exception("Failed to seed ticker snapshot from REST; continuing with WS only")

        return True

    async def _connect_and_stream(self) -> None:
        subscribe_payload = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {
                        "name": "v2/ticker",
                        "symbols": self._symbols + [spot_index_symbol(self.asset)],
                    }
                ]
            },
        }
        async with websockets.connect(
            settings.delta_ws_url,
            ping_interval=settings.ws_ping_interval,
            ping_timeout=settings.ws_ping_interval,
        ) as ws:
            self._active_ws = ws
            try:
                await ws.send(orjson.dumps(subscribe_payload).decode("utf-8"))
                self.status.connected = True
                self.status.reconnect_attempts = 0
                await self.publisher.publish(self.status.to_dict())

                async for raw_message in ws:
                    receive_time = time.time()
                    self.status.last_message_time = receive_time

                    # Delta sends heartbeats/other channel types too; only
                    # ticker payloads matter here, and malformed frames are
                    # dropped rather than crashing the stream.
                    try:
                        message = orjson.loads(raw_message)
                    except orjson.JSONDecodeError:
                        logger.warning("Dropped malformed (non-JSON) WebSocket message")
                        continue

                    if message.get("type") not in ("v2/ticker", "ticker"):
                        continue

                    update = self._apply_ticker(message, broadcast=True)
                    if update is not None:
                        await self.publisher.publish(update)
                        tick_to_publish_seconds.labels(asset=self.asset).observe(time.time() - receive_time)
            finally:
                self._active_ws = None

    def _apply_ticker(self, ticker: dict, broadcast: bool) -> Optional[dict]:
        """Parses one Delta ticker payload, updates the store, and returns
        the WS message to broadcast (or None if there's nothing to send,
        e.g. an incomplete call/put pair or an unrecognized symbol)."""
        symbol = ticker.get("symbol", "")

        if symbol == spot_index_symbol(self.asset):
            spot = ticker.get("spot_price") or ticker.get("close")
            if spot is None:
                return None
            spot = float(spot)
            self.store.set_spot_price(spot)
            return SpotUpdateMessage(asset=self.asset, spotPrice=spot).model_dump() if broadcast else None

        meta = self.resolver.index.lookup(symbol) if self.resolver.index else None
        if meta is None:
            return None
        option_type, strike = meta.option_type, meta.strike

        ltp = ticker.get("close")
        if ltp is None:
            return None
        try:
            ltp = float(ltp)
        except (TypeError, ValueError):
            return None

        if option_type == "C":
            row = self.store.update_call(strike, symbol, ltp)
        else:
            row = self.store.update_put(strike, symbol, ltp)
        ticks_ingested_total.labels(asset=self.asset).inc()

        if not row.is_complete:
            return None  # ignore incomplete call/put pairs until both legs exist

        # feed the straddle into CandleEngine regardless of `broadcast` so
        # REST-seeded bootstrap ticks warm the current bucket too, not just
        # live WS ticks
        self.candles.on_tick(str(strike), row.straddle, time.time() * 1000)
        candle_engine_active_keys.labels(asset=self.asset).set(self.candles.active_count())

        if not broadcast:
            return None

        return RowUpdateMessage(
            asset=self.asset,
            updatedField="call" if option_type == "C" else "put",
            row=OptionRowPayload(**row.to_dict()),
        ).model_dump()
