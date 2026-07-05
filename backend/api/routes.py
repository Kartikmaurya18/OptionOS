from fastapi import APIRouter, Request

from schemas.ws_messages import OptionRowPayload, SnapshotMessage

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/option-chain", response_model=SnapshotMessage)
async def option_chain(request: Request) -> SnapshotMessage:
    """REST fallback mirroring the WS snapshot -- handy for debugging
    without opening a WebSocket client."""
    store = request.app.state.store
    streamer = request.app.state.streamer
    return SnapshotMessage(
        expiry=streamer.status.expiry,
        spotPrice=store.spot_price,
        rows=[OptionRowPayload(**row.to_dict()) for row in store.snapshot(only_complete=True)],
    )
