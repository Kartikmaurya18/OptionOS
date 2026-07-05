import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def fetch_ticker_snapshot(client: httpx.AsyncClient, symbols: list[str]) -> list[dict]:
    """One-shot REST fetch of current tickers for the given symbols, used to
    seed the table immediately on startup rather than waiting for the first
    WebSocket tick per strike.

    Delta's /v2/tickers endpoint does not filter by an arbitrary `symbols`
    list (it's silently ignored and the full market is returned), so we
    request all live BTC option tickers via the same contract_type filter
    /v2/products uses, then narrow to the symbols we actually care about.
    """
    if not symbols:
        return []
    wanted = set(symbols)
    params = {
        "contract_types": "call_options,put_options",
        "underlying_asset_symbols": settings.underlying,
    }
    resp = await client.get(f"{settings.delta_rest_url}/v2/tickers", params=params)
    resp.raise_for_status()
    result = resp.json().get("result", [])
    return [t for t in result if t.get("symbol") in wanted]


async def fetch_spot_price(client: httpx.AsyncClient) -> Optional[float]:
    resp = await client.get(f"{settings.delta_rest_url}/v2/tickers/{settings.spot_index_symbol}")
    resp.raise_for_status()
    result = resp.json().get("result", {})
    price = result.get("spot_price") or result.get("close")
    return float(price) if price is not None else None
