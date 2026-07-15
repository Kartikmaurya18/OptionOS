import asyncio
import logging

import orjson
from fastapi import WebSocket

from observability.metrics import gateway_connected_clients, gateway_dropped_sends_total

logger = logging.getLogger(__name__)


def encode_message(message: dict) -> str:
    """The one JSON encode path for the frontend WS protocol. orjson is a
    drop-in ~3-6x faster replacement for stdlib json.dumps; text frames
    (not bytes) so the frontend's plain JSON.parse(event.data) keeps working
    unchanged."""
    return orjson.dumps(message).decode("utf-8")


class ConnectionManager:
    """Tracks connected frontend WebSocket clients, what each one is
    subscribed to, and fans out broadcasts filtered by that subscription.

    Deliberately decoupled from the Delta Exchange upstream connection: a
    browser tab opening/closing never touches the Delta stream, and the
    Market Data Service doesn't need to know how many tabs are watching, or
    which asset each one wants -- that filtering lives here, at the edge.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._subscriptions[websocket] = set()
        gateway_connected_clients.set(self.client_count)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._subscriptions.pop(websocket, None)
        gateway_connected_clients.set(self.client_count)

    async def subscribe(self, websocket: WebSocket, asset: str) -> None:
        async with self._lock:
            self._subscriptions.setdefault(websocket, set()).add(asset)

    async def unsubscribe(self, websocket: WebSocket, asset: str) -> None:
        async with self._lock:
            subs = self._subscriptions.get(websocket)
            if subs is not None:
                subs.discard(asset)

    async def broadcast(self, message: dict) -> None:
        """Sends `message` only to clients subscribed to its `asset`. A
        message with no `asset` field (there currently are none, but this
        keeps the method safe for future asset-agnostic messages) goes to
        everyone."""
        asset = message.get("asset")
        payload = encode_message(message)  # serialize once, not once per client

        async with self._lock:
            targets = [
                ws for ws, subs in self._subscriptions.items() if asset is None or asset in subs
            ]

        stale: list[WebSocket] = []
        for client in targets:
            try:
                await client.send_text(payload)
            except Exception:
                stale.append(client)

        if stale:
            gateway_dropped_sends_total.inc(len(stale))
            async with self._lock:
                for client in stale:
                    self._subscriptions.pop(client, None)
            gateway_connected_clients.set(self.client_count)

    @property
    def client_count(self) -> int:
        return len(self._subscriptions)
