import { tickStore } from "@/lib/tickStore";
import { DEFAULT_ASSET, optionStore } from "@/services/optionStore";
import type { ClientCommand, ServerMessage } from "@/types/options";

const DEFAULT_WS_URL = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.hostname}:8000/ws`;
const WS_URL = import.meta.env.VITE_WS_URL || DEFAULT_WS_URL;

const MIN_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;

let socket: WebSocket | null = null;
let reconnectDelay = MIN_RECONNECT_DELAY_MS;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let manuallyClosed = false;
let currentAsset = DEFAULT_ASSET;

function send(command: ClientCommand): void {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(command));
}

function scheduleReconnect(): void {
  if (manuallyClosed || reconnectTimer !== null) return;
  optionStore.incrementLocalReconnectAttempts();
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
}

function connect(): void {
  socket = new WebSocket(WS_URL);

  socket.onopen = () => {
    reconnectDelay = MIN_RECONNECT_DELAY_MS;
    optionStore.setSocketOpen(true);
    send({ type: "subscribe", asset: currentAsset });
  };

  socket.onmessage = (event: MessageEvent<string>) => {
    optionStore.recordMessageReceived();

    let message: ServerMessage;
    try {
      message = JSON.parse(event.data);
    } catch {
      return; // dropped malformed frame
    }
    optionStore.dispatch(message);
    tickStore.ingest(message);
  };

  socket.onclose = () => {
    optionStore.setSocketOpen(false);
    socket = null;
    scheduleReconnect();
  };

  socket.onerror = () => {
    socket?.close();
  };
}

/** Opens the socket to our FastAPI backend and returns a teardown function.
 * The frontend never talks to Delta Exchange directly -- this is the only
 * WebSocket it knows about. Subscribes to `initialAsset` (or the default)
 * as soon as the connection opens. */
export function connectOptionsSocket(initialAsset: string = DEFAULT_ASSET): () => void {
  manuallyClosed = false;
  currentAsset = initialAsset;
  connect();

  return () => {
    manuallyClosed = true;
    if (reconnectTimer !== null) clearTimeout(reconnectTimer);
    socket?.close();
    socket = null;
  };
}

/** Switches the live subscription to a different asset: unsubscribes the
 * old one, clears local state so nothing from it lingers on screen, then
 * subscribes to the new one and waits for its snapshot. */
export function switchAsset(asset: string): void {
  if (asset === currentAsset) return;
  send({ type: "unsubscribe", asset: currentAsset });
  currentAsset = asset;
  optionStore.switchAsset(asset);
  tickStore.switchAsset(asset);
  send({ type: "subscribe", asset });
}
