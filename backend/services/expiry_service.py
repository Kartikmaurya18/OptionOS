import logging
from datetime import datetime
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def fetch_option_products(client: httpx.AsyncClient) -> list[dict]:
    """Fetch all live BTC call/put option products from Delta's REST API."""
    params = {
        "contract_types": "call_options,put_options",
        "states": "live",
        "underlying_asset_symbols": settings.underlying,
    }
    resp = await client.get(f"{settings.delta_rest_url}/v2/products", params=params)
    resp.raise_for_status()
    return resp.json().get("result", [])


def _expiry_from_symbol(symbol: str) -> Optional[tuple[str, datetime]]:
    """Option symbols look like 'C-BTC-95000-040726' (ddmmyy expiry)."""
    parts = symbol.split("-")
    if len(parts) != 4:
        return None
    expiry_key = parts[3]
    try:
        expiry_dt = datetime.strptime(expiry_key, "%d%m%y")
    except ValueError:
        return None
    return expiry_key, expiry_dt


async def resolve_nearest_expiry(client: httpx.AsyncClient) -> tuple[str, list[dict]]:
    """Group live BTC option products by expiry and return the soonest
    upcoming expiry (ddmmyy) along with just that expiry's products."""
    products = await fetch_option_products(client)

    now = datetime.utcnow()
    by_expiry: dict[str, list[dict]] = {}
    expiry_dates: dict[str, datetime] = {}

    for product in products:
        parsed = _expiry_from_symbol(product.get("symbol", ""))
        if parsed is None:
            continue
        expiry_key, expiry_dt = parsed
        by_expiry.setdefault(expiry_key, []).append(product)
        expiry_dates[expiry_key] = expiry_dt

    upcoming = {k: v for k, v in expiry_dates.items() if v >= now}
    if not upcoming:
        raise RuntimeError("No upcoming BTC option expiries found on Delta Exchange")

    nearest_key = min(upcoming, key=lambda k: upcoming[k])
    logger.info(
        "Resolved nearest BTC options expiry: %s (%d strikes' worth of products)",
        nearest_key,
        len(by_expiry[nearest_key]),
    )
    return nearest_key, by_expiry[nearest_key]
