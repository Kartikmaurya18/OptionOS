import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from schemas.ws_messages import OptionRowPayload, SnapshotMessage

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def options_ws(websocket: WebSocket) -> None:
    """The only WebSocket route the frontend talks to. Delta Exchange
    credentials/connection details never reach the browser."""
    store = websocket.app.state.store
    manager = websocket.app.state.manager
    streamer = websocket.app.state.streamer

    await manager.connect(websocket)
    try:
        snapshot = SnapshotMessage(
            expiry=streamer.status.expiry,
            spotPrice=store.spot_price,
            rows=[OptionRowPayload(**row.to_dict()) for row in store.snapshot(only_complete=True)],
        )
        await websocket.send_json(snapshot.model_dump())
        await websocket.send_json(streamer.status.to_dict())

        while True:
            # The frontend never sends anything meaningful, but we must
            # keep awaiting incoming frames -- it's how FastAPI notices
            # the client closing the connection.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
