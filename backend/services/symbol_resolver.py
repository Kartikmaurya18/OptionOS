import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from config import settings
from services.expiry_service import resolve_nearest_expiry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SymbolMeta:
    """What a raw option symbol decodes to: which leg, which strike."""

    option_type: str  # "C" or "P"
    strike: float


@dataclass(slots=True)
class SymbolIndex:
    """One expiry's resolved option chain. Built once per chain refresh so
    the tick hot path is a dict lookup (symbol -> SymbolMeta) instead of a
    string split per message.
    """

    expiry: str
    strikes: list[float] = field(default_factory=list)
    call_symbol_by_strike: dict[float, str] = field(default_factory=dict)
    put_symbol_by_strike: dict[float, str] = field(default_factory=dict)
    meta_by_symbol: dict[str, SymbolMeta] = field(default_factory=dict)

    @property
    def all_symbols(self) -> list[str]:
        return list(self.meta_by_symbol.keys())

    def lookup(self, symbol: str) -> Optional[SymbolMeta]:
        return self.meta_by_symbol.get(symbol)


def parse_option_symbol(symbol: str, underlying: Optional[str] = None) -> Optional[SymbolMeta]:
    """Delta option symbols follow '<C|P>-<underlying>-<strike>-<expiry ddmmyy>',
    e.g. 'C-BTC-95000-040726'. Returns None if the symbol isn't an option for
    `underlying` (e.g. it's the perpetual/index symbol, or malformed) so
    callers can safely ignore it.
    """
    parts = symbol.split("-")
    if len(parts) != 4:
        return None
    option_type, sym_underlying, strike_str, _expiry = parts
    if option_type not in ("C", "P") or sym_underlying != (underlying or settings.underlying):
        return None
    try:
        strike = float(strike_str)
    except ValueError:
        return None
    return SymbolMeta(option_type=option_type, strike=strike)


class SymbolResolver:
    """Resolves the live option chain for one underlying and caches it as a
    SymbolIndex. Pure/stateless aside from that cache -- no OptionStore
    dependency, safe to call from any shard's event loop.
    """

    def __init__(self, underlying: Optional[str] = None) -> None:
        self.underlying = underlying or settings.underlying
        self._index: Optional[SymbolIndex] = None

    @property
    def index(self) -> Optional[SymbolIndex]:
        return self._index

    async def resolve(self, http_client: httpx.AsyncClient) -> SymbolIndex:
        expiry, products = await resolve_nearest_expiry(http_client, self.underlying)
        index = SymbolIndex(expiry=expiry)
        strikes_seen: set[float] = set()

        for product in products:
            symbol = product.get("symbol", "")
            parsed = parse_option_symbol(symbol, self.underlying)
            if parsed is None:
                continue

            index.meta_by_symbol[symbol] = parsed
            if parsed.strike not in strikes_seen:
                strikes_seen.add(parsed.strike)
                index.strikes.append(parsed.strike)

            if parsed.option_type == "C":
                index.call_symbol_by_strike[parsed.strike] = symbol
                index.put_symbol_by_strike.setdefault(parsed.strike, symbol.replace("C-", "P-", 1))
            else:
                index.put_symbol_by_strike[parsed.strike] = symbol

        index.strikes.sort()
        self._index = index
        logger.info(
            "Resolved %s option chain: %d strikes, expiry %s",
            self.underlying,
            len(index.strikes),
            expiry,
        )
        return index
