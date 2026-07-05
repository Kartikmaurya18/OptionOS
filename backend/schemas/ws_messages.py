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
    """Sent once, right after a frontend client connects, so the table
    isn't empty while waiting for the next live tick."""

    type: Literal["snapshot"] = "snapshot"
    expiry: Optional[str] = None
    spotPrice: Optional[float] = None
    rows: list[OptionRowPayload]


class RowUpdateMessage(BaseModel):
    """Sent whenever a single strike's call or put leg changes. The
    frontend patches only this row instead of re-rendering the table."""

    type: Literal["row_update"] = "row_update"
    updatedField: Literal["call", "put"]
    row: OptionRowPayload


class SpotUpdateMessage(BaseModel):
    type: Literal["spot_update"] = "spot_update"
    spotPrice: float


class StatusMessage(BaseModel):
    """Drives the header's connection/status widgets."""

    type: Literal["status"] = "status"
    connected: bool
    reconnectAttempts: int
    lastMessageTime: Optional[float] = None
    expiry: Optional[str] = None
    strikeCount: int = 0
