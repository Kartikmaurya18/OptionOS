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
  asset: string;
  expiry: string | null;
  spotPrice: number | null;
  rows: OptionRow[];
}

export interface RowUpdateMessage {
  type: "row_update";
  asset: string;
  updatedField: "call" | "put";
  row: OptionRow;
}

export interface SpotUpdateMessage {
  type: "spot_update";
  asset: string;
  spotPrice: number;
}

export interface CandlePayload {
  time: number; // epoch ms, start of the bucket
  open: number;
  high: number;
  low: number;
  close: number;
  tickCount: number;
}

export interface CandleUpdateMessage {
  type: "candle_update";
  asset: string;
  strike: number;
  timeframe: string;
  candle: CandlePayload;
}

export interface StatusMessage {
  type: "status";
  asset: string;
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
  | CandleUpdateMessage
  | StatusMessage;

// Client -> server: select which asset's option chain to receive.
export interface SubscribeCommand {
  type: "subscribe";
  asset: string;
}

export interface UnsubscribeCommand {
  type: "unsubscribe";
  asset: string;
}

export type ClientCommand = SubscribeCommand | UnsubscribeCommand;

export type SortColumn = "strike" | "call" | "put" | "straddle";
export type SortDirection = "asc" | "desc";

export type ConnectionPhase = "connecting" | "connected" | "disconnected";

export interface HeaderStats {
  asset: string;
  spotPrice: number | null;
  expiry: string | null;
  phase: ConnectionPhase;
  reconnectAttempts: number;
  lastMessageTime: number | null;
  strikeCount: number;
}
