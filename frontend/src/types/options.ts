// Mirrors backend/schemas/ws_messages.py -- keep in sync with that file.

export interface OptionRow {
  strike: number;
  callSymbol: string;
  putSymbol: string;
  callLtp: number | null;
  putLtp: number | null;
  straddle: number | null;
  lastUpdated: number;
}

export interface SnapshotMessage {
  type: "snapshot";
  expiry: string | null;
  spotPrice: number | null;
  rows: OptionRow[];
}

export interface RowUpdateMessage {
  type: "row_update";
  updatedField: "call" | "put";
  row: OptionRow;
}

export interface SpotUpdateMessage {
  type: "spot_update";
  spotPrice: number;
}

export interface StatusMessage {
  type: "status";
  connected: boolean;
  reconnectAttempts: number;
  lastMessageTime: number | null;
  expiry: string | null;
  strikeCount: number;
}

export type ServerMessage =
  | SnapshotMessage
  | RowUpdateMessage
  | SpotUpdateMessage
  | StatusMessage;

export type SortColumn = "strike" | "call" | "put" | "straddle";
export type SortDirection = "asc" | "desc";

export type ConnectionPhase = "connecting" | "connected" | "disconnected";

export interface HeaderStats {
  spotPrice: number | null;
  expiry: string | null;
  phase: ConnectionPhase;
  reconnectAttempts: number;
  lastMessageTime: number | null;
  strikeCount: number;
}
