import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class OptionRow:
    """One strike's worth of state: its call leg, put leg, and the derived
    straddle. Mutated in place by OptionStore so a price tick only ever
    touches the one row it affects, never the whole table.
    """

    strike: float
    call_symbol: str
    put_symbol: str
    call_ltp: Optional[float] = None
    put_ltp: Optional[float] = None
    last_updated: float = field(default_factory=time.time)

    @property
    def straddle(self) -> Optional[float]:
        if self.call_ltp is None or self.put_ltp is None:
            return None
        return round(self.call_ltp + self.put_ltp, 2)

    @property
    def is_complete(self) -> bool:
        return self.call_ltp is not None and self.put_ltp is not None

    def to_dict(self) -> dict:
        return {
            "strike": self.strike,
            "callSymbol": self.call_symbol,
            "putSymbol": self.put_symbol,
            "callLtp": self.call_ltp,
            "putLtp": self.put_ltp,
            "straddle": self.straddle,
            "lastUpdated": self.last_updated,
        }
