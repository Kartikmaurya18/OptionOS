import time

from fastapi import APIRouter, Query, Request

from observability.metrics import backfill_query_seconds

router = APIRouter(prefix="/api")


@router.get("/candles")
async def candles(
    request: Request,
    asset: str,
    strike: float,
    timeframe: str,
    start: int = Query(..., alias="from", description="epoch ms, inclusive"),
    end: int = Query(..., alias="to", description="epoch ms, exclusive"),
) -> dict:
    """HistoricalBackfillService: closed candles for one instrument/timeframe
    over [from, to). Called once when a chart mounts, before it subscribes
    to the live WS feed for the same instrument -- see frontend
    hooks/useCandleBackfill.ts."""
    started = time.time()
    store = request.app.state.clickhouse
    rows = await store.query_candles(asset, strike, timeframe, start, end)
    backfill_query_seconds.labels(asset=asset).observe(time.time() - started)
    return {"candles": rows}
