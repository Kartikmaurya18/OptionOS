import asyncio
import json
import logging
import time
from typing import Optional

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from config import settings
from schemas.ws_messages import OptionRowPayload, RowUpdateMessage, SpotUpdateMessage, StatusMessage
from services.delta_rest import fetch_ticker_snapshot
from services.expiry_service import resolve_nearest_expiry
from services.option_store import OptionStore
from websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


def parse_option_symbol(symbol: str) -> Optional[tuple[str, float]]:
    """Delta option symbols follow '<C|P>-<underlying>-<strike>-<expiry ddmmyy>',
    e.g. 'C-BTC-95000-040726'. Returns (option_type, strike), or None if the
    symbol isn't a BTC option (e.g. it's the perpetual/index symbol, or
    malformed) so callers can safely ignore it.
    """
    parts = symbol.split("-")
    if len(parts) != 4:
        return None
    option_type, underlying, strike_str, _expiry = parts
    if option_type not in ("C", "P") or underlying != settings.underlying:
        return None
    try:
        strike = float(strike_str)
    except ValueError:
        return None
    return option_type, strike


class DeltaStreamStatus:
    """Live connection state surfaced to the frontend header bar."""

    def __init__(self) -> None:
        self.connected = False
        self.reconnect_attempts = 0
        self.last_message_time: Optional[float] = None
        self.expiry: Optional[str] = None
        self.strike_count = 0

    def to_dict(self) -> dict:
        return StatusMessage(
            connected=self.connected,
            reconnectAttempts=self.reconnect_attempts,
            lastMessageTime=self.last_message_time,
            expiry=self.expiry,
            strikeCount=self.strike_count,
        ).model_dump()


class DeltaOptionsStreamer:
    """Owns the upstream connection to Delta Exchange's public WebSocket.

    Resolves the nearest BTC options expiry, subscribes to v2/ticker for
    every call/put symbol in that chain plus the BTC spot index, keeps
    OptionStore updated, and pushes single-row diffs to the frontend via
    ConnectionManager. Runs forever, reconnecting with exponential backoff
    on any drop (network error, Delta restart, etc).
    """

    def __init__(self, store: OptionStore, manager: ConnectionManager) -> None:
        self.store = store
        self.manager = manager
        self.status = DeltaStreamStatus()
        self._symbols: list[str] = []

    async def run_forever(self) -> None:
        delay = settings.ws_reconnect_min_delay
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            while True:
                try:
                    if self.status.expiry is None:
                        await self._bootstrap(http_client)

                    await self._connect_and_stream()
                    delay = settings.ws_reconnect_min_delay
                except (ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
                    logger.warning("Delta WebSocket disconnected: %s", exc)
                except Exception:
                    logger.exception("Unexpected error in Delta stream loop")

                self.status.connected = False
                self.status.reconnect_attempts += 1
                await self.manager.broadcast(self.status.to_dict())
                await asyncio.sleep(delay)
                delay = min(delay * 2, settings.ws_reconnect_max_delay)

    async def _bootstrap(self, http_client: httpx.AsyncClient) -> None:
        """One-time setup: resolve the nearest expiry, register every strike
        in the store, and seed it with a REST snapshot before streaming."""
        expiry, products = await resolve_nearest_expiry(http_client)
        self.status.expiry = expiry
        self._symbols = self._index_products(products)
        self.status.strike_count = self.store.row_count()

        try:
            tickers = await fetch_ticker_snapshot(http_client, self._symbols)
            for ticker in tickers:
                self._apply_ticker(ticker, broadcast=False)
        except Exception:
            logger.exception("Failed to seed initial ticker snapshot from REST; continuing with WS only")

    def _index_products(self, products: list[dict]) -> list[str]:
        """Registers a store row per strike and returns every option symbol
        (call + put) that should be subscribed to on the WebSocket."""
        symbols: list[str] = []
        for product in products:
            symbol = product.get("symbol", "")
            parsed = parse_option_symbol(symbol)
            if parsed is None:
                continue
            option_type, strike = parsed
            symbols.append(symbol)
            if option_type == "C":
                put_symbol = symbol.replace("C-", "P-", 1)
                self.store.ensure_row(strike, symbol, put_symbol)
        return symbols

    async def _connect_and_stream(self) -> None:
        subscribe_payload = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {
                        "name": "v2/ticker",
                        "symbols": self._symbols + [settings.spot_index_symbol],
                    }
                ]
            },
        }
        async with websockets.connect(
            settings.delta_ws_url,
            ping_interval=settings.ws_ping_interval,
            ping_timeout=settings.ws_ping_interval,
        ) as ws:
            await ws.send(json.dumps(subscribe_payload))
            self.status.connected = True
            self.status.reconnect_attempts = 0
            await self.manager.broadcast(self.status.to_dict())

            async for raw_message in ws:
                self.status.last_message_time = time.time()

                # Delta sends heartbeats/other channel types too; only
                # ticker payloads matter here, and malformed frames are
                # dropped rather than crashing the stream.
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    logger.warning("Dropped malformed (non-JSON) WebSocket message")
                    continue

                if message.get("type") not in ("v2/ticker", "ticker"):
                    continue

                update = self._apply_ticker(message, broadcast=True)
                if update is not None:
                    await self.manager.broadcast(update)

    def _apply_ticker(self, ticker: dict, broadcast: bool) -> Optional[dict]:
        """Parses one Delta ticker payload, updates the store, and returns
        the WS message to broadcast (or None if there's nothing to send,
        e.g. an incomplete call/put pair or an unrecognized symbol)."""
        symbol = ticker.get("symbol", "")

        if symbol == settings.spot_index_symbol:
            spot = ticker.get("spot_price") or ticker.get("close")
            if spot is None:
                return None
            spot = float(spot)
            self.store.set_spot_price(spot)
            return SpotUpdateMessage(spotPrice=spot).model_dump() if broadcast else None

        parsed = parse_option_symbol(symbol)
        if parsed is None:
            return None
        option_type, strike = parsed

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

        if not row.is_complete:
            return None  # ignore incomplete call/put pairs until both legs exist

        if not broadcast:
            return None

        return RowUpdateMessage(
            updatedField="call" if option_type == "C" else "put",
            row=OptionRowPayload(**row.to_dict()),
        ).model_dump()
