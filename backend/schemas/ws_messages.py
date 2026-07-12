from typing import Literal, Optional

from pydantic import BaseModel


class OptionRowPayload(BaseModel):
    strike: float
    callSymbol: str
    putSymbol: str
    callLtp: Optional[float] = None
    putLtp: Optional[float] = None
    straddle: Optional[float] = None
    lastUpdated: float


class SnapshotMessage(BaseModel):
    """Sent once a client subscribes to an asset, so the table isn't empty
    while waiting for the next live tick."""

    type: Literal["snapshot"] = "snapshot"
    asset: str
    expiry: Optional[str] = None
    spotPrice: Optional[float] = None
    rows: list[OptionRowPayload]


class RowUpdateMessage(BaseModel):
    """Sent whenever a single strike's call or put leg changes. The
    frontend patches only this row instead of re-rendering the table."""

    type: Literal["row_update"] = "row_update"
    asset: str
    updatedField: Literal["call", "put"]
    row: OptionRowPayload


class SpotUpdateMessage(BaseModel):
    type: Literal["spot_update"] = "spot_update"
    asset: str
    spotPrice: float


class CandlePayload(BaseModel):
    time: int  # epoch ms, start of the bucket
    open: float
    high: float
    low: float
    close: float
    tickCount: int


class CandleUpdateMessage(BaseModel):
    """Sent whenever CandleEngine closes a bucket for one strike/timeframe.
    Carries a single finished candle -- the frontend appends/updates it on
    the chart series directly, no client-side rebucketing required."""

    type: Literal["candle_update"] = "candle_update"
    asset: str
    strike: float
    timeframe: str
    candle: CandlePayload


class StatusMessage(BaseModel):
    """Drives the header's connection/status widgets."""

    type: Literal["status"] = "status"
    asset: str
    connected: bool
    reconnectAttempts: int
    lastMessageTime: Optional[float] = None
    expiry: Optional[str] = None
    strikeCount: int = 0


class SubscribeCommand(BaseModel):
    """Sent by the client to select which asset's option chain it wants to
    receive. ConnectionManager filters every broadcast by this."""

    type: Literal["subscribe"] = "subscribe"
    asset: str


class UnsubscribeCommand(BaseModel):
    type: Literal["unsubscribe"] = "unsubscribe"
    asset: str
