from fastapi import APIRouter, HTTPException, Request

from config import settings
from schemas.ws_messages import OptionRowPayload, SnapshotMessage

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/assets")
async def assets() -> dict:
    """Which asset shards this backend is running -- lets the frontend
    build its asset switcher without hardcoding the list."""
    return {"assets": settings.assets, "default": settings.underlying}


@router.get("/option-chain", response_model=SnapshotMessage)
async def option_chain(request: Request, asset: str = settings.underlying) -> SnapshotMessage:
    """REST fallback mirroring the WS snapshot -- handy for debugging
    without opening a WebSocket client."""
    stores = request.app.state.stores
    streamers = request.app.state.streamers
    if asset not in stores:
        raise HTTPException(status_code=404, detail=f"Unknown asset '{asset}'; configured assets: {settings.assets}")
    store = stores[asset]
    streamer = streamers[asset]
    return SnapshotMessage(
        asset=asset,
        expiry=streamer.status.expiry,
        spotPrice=store.spot_price,
        rows=[OptionRowPayload(**row.to_dict()) for row in store.snapshot(only_complete=True)],
    )
