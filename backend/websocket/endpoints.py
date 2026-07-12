import logging

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from schemas.ws_messages import OptionRowPayload, SnapshotMessage
from websocket.manager import encode_message

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def options_ws(websocket: WebSocket) -> None:
    """The only WebSocket route the frontend talks to. Delta Exchange
    credentials/connection details never reach the browser.

    Protocol: the client must send {"type": "subscribe", "asset": "BTC"}
    after connecting (services/socket.ts does this immediately on open). A
    freshly connected client receives nothing until it subscribes -- there's
    no default asset at this layer, since ConnectionManager only knows how
    to filter, not which asset a silent client might want. Subscribing
    triggers an immediate snapshot + status for that asset; {"type":
    "unsubscribe", "asset": "BTC"} stops further updates for it (e.g. when
    the user switches assets in the UI).
    """
    stores = websocket.app.state.stores
    streamers = websocket.app.state.streamers
    manager = websocket.app.state.manager

    await manager.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                command = orjson.loads(raw)
            except orjson.JSONDecodeError:
                logger.warning("Dropped malformed (non-JSON) client command")
                continue

            asset = command.get("asset")
            if asset not in stores:
                continue  # unknown/unconfigured asset -- ignore rather than error

            if command.get("type") == "subscribe":
                await manager.subscribe(websocket, asset)
                store = stores[asset]
                streamer = streamers[asset]
                snapshot = SnapshotMessage(
                    asset=asset,
                    expiry=streamer.status.expiry,
                    spotPrice=store.spot_price,
                    rows=[OptionRowPayload(**row.to_dict()) for row in store.snapshot(only_complete=True)],
                )
                await websocket.send_text(encode_message(snapshot.model_dump()))
                await websocket.send_text(encode_message(streamer.status.to_dict()))
            elif command.get("type") == "unsubscribe":
                await manager.unsubscribe(websocket, asset)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
