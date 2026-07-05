import time
from typing import Optional

from models.option_row import OptionRow


class OptionStore:
    """The single in-memory source of truth: strike -> OptionRow.

    Runs entirely on the asyncio event loop (no threads touch it), so plain
    dict mutation is safe without extra locking. update_call/update_put
    mutate the existing row object in place and return it, which is what
    lets callers broadcast a single-row diff instead of the whole table.
    """

    def __init__(self) -> None:
        self._rows: dict[float, OptionRow] = {}
        self._spot_price: Optional[float] = None

    def ensure_row(self, strike: float, call_symbol: str, put_symbol: str) -> OptionRow:
        row = self._rows.get(strike)
        if row is None:
            row = OptionRow(strike=strike, call_symbol=call_symbol, put_symbol=put_symbol)
            self._rows[strike] = row
        return row

    def update_call(self, strike: float, symbol: str, ltp: float) -> OptionRow:
        row = self._rows.get(strike)
        if row is None:
            row = OptionRow(strike=strike, call_symbol=symbol, put_symbol="")
            self._rows[strike] = row
        row.call_symbol = symbol
        row.call_ltp = ltp
        row.last_updated = time.time()
        return row

    def update_put(self, strike: float, symbol: str, ltp: float) -> OptionRow:
        row = self._rows.get(strike)
        if row is None:
            row = OptionRow(strike=strike, call_symbol="", put_symbol=symbol)
            self._rows[strike] = row
        row.put_symbol = symbol
        row.put_ltp = ltp
        row.last_updated = time.time()
        return row

    def set_spot_price(self, price: float) -> None:
        self._spot_price = price

    @property
    def spot_price(self) -> Optional[float]:
        return self._spot_price

    def snapshot(self, only_complete: bool = True) -> list[OptionRow]:
        rows = self._rows.values()
        if only_complete:
            rows = (r for r in rows if r.is_complete)
        return sorted(rows, key=lambda r: r.strike)

    def row_count(self) -> int:
        return len(self._rows)
