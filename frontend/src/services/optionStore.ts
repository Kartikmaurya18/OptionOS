import type {
  ConnectionPhase,
  HeaderStats,
  OptionRow,
  RowUpdateMessage,
  ServerMessage,
  SnapshotMessage,
  SpotUpdateMessage,
  StatusMessage,
} from "@/types/options";

type Listener = () => void;

/**
 * Central client-side option map: strike -> OptionRow, mirroring one
 * asset's shard of the backend's store. Rows are REPLACED (not mutated in
 * place) on update so useSyncExternalStore's Object.is check sees a new
 * reference only for the strike that actually changed -- every other
 * strike's Map entry keeps its old reference, so its subscriber sees
 * "nothing changed" and skips re-rendering. That's what makes "only the
 * affected row re-renders" hold at the React level, not just conceptually.
 *
 * Holds exactly one asset's data at a time (not all configured assets
 * simultaneously) -- switchAsset() clears everything and starts fresh,
 * mirroring the backend dropping the old subscription and sending a new
 * snapshot for the newly selected asset.
 */
class OptionStore {
  private asset: string;
  private rows = new Map<number, OptionRow>();
  private strikes: number[] = [];
  private rowListeners = new Map<number, Set<Listener>>();
  private strikeListeners = new Set<Listener>();
  private headerListeners = new Set<Listener>();

  private spotPrice: number | null = null;
  private expiry: string | null = null;
  private strikeCount = 0;
  private lastMessageTime: number | null = null;

  private upstreamConnected = false;
  private upstreamReconnectAttempts = 0;

  private socketOpen = false;
  private everConnectedSocket = false;
  private localReconnectAttempts = 0;

  private headerSnapshot: HeaderStats;

  constructor(initialAsset: string) {
    this.asset = initialAsset;
    this.headerSnapshot = this.computeHeaderSnapshot();
  }

  // ---- asset selection ----

  getAsset(): string {
    return this.asset;
  }

  /** Called by services/socket.ts right before it sends the subscribe
   * command for a new asset -- clears every strike/row so nothing from the
   * previous asset lingers on screen while the new snapshot is in flight. */
  switchAsset(asset: string): void {
    if (asset === this.asset) return;
    this.asset = asset;
    this.rows = new Map();
    this.strikes = [];
    this.spotPrice = null;
    this.expiry = null;
    this.strikeCount = 0;

    for (const strike of this.rowListeners.keys()) this.notifyRow(strike);
    this.notifyStrikes();
    this.notifyHeader();
  }

  // ---- rows ----

  getRow(strike: number): OptionRow | undefined {
    return this.rows.get(strike);
  }

  getStrikes(): number[] {
    return this.strikes;
  }

  subscribeRow(strike: number, listener: Listener): () => void {
    let set = this.rowListeners.get(strike);
    if (!set) {
      set = new Set();
      this.rowListeners.set(strike, set);
    }
    set.add(listener);
    return () => set.delete(listener);
  }

  subscribeStrikes(listener: Listener): () => void {
    this.strikeListeners.add(listener);
    return () => this.strikeListeners.delete(listener);
  }

  private notifyRow(strike: number): void {
    for (const listener of this.rowListeners.get(strike) ?? []) listener();
  }

  private notifyStrikes(): void {
    for (const listener of this.strikeListeners) listener();
  }

  // ---- header stats ----

  getHeaderStats(): HeaderStats {
    return this.headerSnapshot;
  }

  subscribeHeaderStats(listener: Listener): () => void {
    this.headerListeners.add(listener);
    return () => this.headerListeners.delete(listener);
  }

  private notifyHeader(): void {
    this.headerSnapshot = this.computeHeaderSnapshot();
    for (const listener of this.headerListeners) listener();
  }

  private computeHeaderSnapshot(): HeaderStats {
    let phase: ConnectionPhase;
    let reconnectAttempts: number;

    if (!this.socketOpen) {
      phase = this.everConnectedSocket ? "disconnected" : "connecting";
      reconnectAttempts = this.localReconnectAttempts;
    } else if (!this.upstreamConnected) {
      phase = "disconnected";
      reconnectAttempts = this.upstreamReconnectAttempts;
    } else {
      phase = "connected";
      reconnectAttempts = 0;
    }

    return {
      asset: this.asset,
      spotPrice: this.spotPrice,
      expiry: this.expiry,
      strikeCount: this.strikeCount,
      lastMessageTime: this.lastMessageTime,
      phase,
      reconnectAttempts,
    };
  }

  // ---- socket lifecycle (called by services/socket.ts) ----

  setSocketOpen(open: boolean): void {
    this.socketOpen = open;
    if (open) {
      this.everConnectedSocket = true;
      this.localReconnectAttempts = 0;
    }
    this.notifyHeader();
  }

  incrementLocalReconnectAttempts(): void {
    this.localReconnectAttempts += 1;
    this.notifyHeader();
  }

  /** Called on every inbound message regardless of type, so "Last Updated
   * Time" reflects real traffic rather than the rarer backend `status`
   * broadcasts (which only fire on connect/disconnect transitions). */
  recordMessageReceived(): void {
    this.lastMessageTime = Date.now();
    this.notifyHeader();
  }

  // ---- message application ----

  dispatch(message: ServerMessage): void {
    // The gateway filters by subscription server-side, but a message for
    // the asset we just switched away from can still be in flight when we
    // switch -- drop it locally rather than let it repopulate a store the
    // user just cleared.
    if ("asset" in message && message.asset !== this.asset) return;

    switch (message.type) {
      case "snapshot":
        this.applySnapshot(message);
        break;
      case "row_update":
        this.applyRowUpdate(message);
        break;
      case "spot_update":
        this.applySpotUpdate(message);
        break;
      case "status":
        this.applyStatus(message);
        break;
      case "candle_update":
        break; // handled by tickStore, not the row/table store
    }
  }

  private applySnapshot(msg: SnapshotMessage): void {
    const newRows = new Map<number, OptionRow>();
    const newStrikes: number[] = [];
    for (const row of msg.rows) {
      newRows.set(row.strike, row);
      newStrikes.push(row.strike);
    }
    this.rows = newRows;
    this.strikes = newStrikes;
    this.spotPrice = msg.spotPrice;
    this.expiry = msg.expiry;
    this.strikeCount = msg.rows.length;

    // Covers reconnects where a fresh snapshot replaces already-rendered
    // rows, not just the initial (pre-mount) load.
    for (const strike of this.rowListeners.keys()) this.notifyRow(strike);
    this.notifyStrikes();
    this.notifyHeader();
  }

  private applyRowUpdate(msg: RowUpdateMessage): void {
    const { row } = msg;
    const isNewStrike = !this.rows.has(row.strike);
    this.rows.set(row.strike, row);

    if (isNewStrike) {
      this.strikes = [...this.strikes, row.strike];
      this.strikeCount = this.strikes.length;
      this.notifyStrikes();
      this.notifyHeader();
    }

    this.notifyRow(row.strike);
  }

  private applySpotUpdate(msg: SpotUpdateMessage): void {
    this.spotPrice = msg.spotPrice;
    this.notifyHeader();
  }

  private applyStatus(msg: StatusMessage): void {
    this.upstreamConnected = msg.connected;
    this.upstreamReconnectAttempts = msg.reconnectAttempts;
    if (msg.expiry) this.expiry = msg.expiry;
    if (msg.strikeCount) this.strikeCount = msg.strikeCount;
    this.notifyHeader();
  }
}

export const DEFAULT_ASSET = "BTC";
export const optionStore = new OptionStore(DEFAULT_ASSET);
