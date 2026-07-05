// Tick ingestion + storage for the straddle chart. Decoupled from the
// WebSocket/UI: `services/socket.ts` calls `tickStore.ingest(message)` once
// per inbound message, and `useStraddleCandles` reads from here.
//
// Persistence is IndexedDB rather than localStorage: a conservative rate
// (26 strikes updating a few times a minute over 24h) is tens of thousands
// of rows, localStorage is synchronous and string-only (JSON.stringify of a
// growing array on every write would block the main thread) and capped
// around 5-10MB. IndexedDB is async, comfortably handles this volume, and
// its timestamp index lets the 24h eviction sweep run as a cheap
// range-delete instead of reading everything back into memory.

import type { ServerMessage } from "@/types/options";

export interface Tick {
  timestamp: number;
  value: number;
}

interface StoredTick extends Tick {
  strike: number;
}

type Listener = () => void;

const DB_NAME = "straddle-ticks";
const DB_VERSION = 1;
const STORE_NAME = "ticks";

const ROLLING_WINDOW_MS = 24 * 60 * 60 * 1000;
const FLUSH_INTERVAL_MS = 2000;
const EVICTION_SWEEP_INTERVAL_MS = 5 * 60 * 1000;

const hasIndexedDb = typeof indexedDB !== "undefined";

class TickStore {
  // Rolling in-memory buffer per strike. Ticks arrive in non-decreasing
  // timestamp order (real-time feed), so eviction is just trimming the
  // front once entries age out -- no need to re-scan the whole array.
  private buffers = new Map<number, Tick[]>();

  // Bumped on every recordTick for a strike; lets consumers (see
  // useStraddleCandles) know whether they need to recompute candles or can
  // reuse a cached array, instead of recomputing on every render.
  private versions = new Map<number, number>();

  private listeners = new Map<number, Set<Listener>>();

  // New ticks are queued here and flushed to IndexedDB in one batched
  // transaction every FLUSH_INTERVAL_MS, instead of one transaction per tick.
  private writeQueue: StoredTick[] = [];

  private dbPromise: Promise<IDBDatabase> | null = null;

  constructor() {
    if (hasIndexedDb) {
      this.openDb()
        .then((db) => this.hydrateAll(db))
        .catch((err: unknown) => console.error("tickStore: failed to hydrate from IndexedDB", err));
      setInterval(() => void this.flush(), FLUSH_INTERVAL_MS);
      setInterval(() => void this.evictOld(), EVICTION_SWEEP_INTERVAL_MS);
    }
  }

  getTicks(strike: number): Tick[] {
    return this.buffers.get(strike) ?? [];
  }

  getVersion(strike: number): number {
    return this.versions.get(strike) ?? 0;
  }

  subscribe(strike: number, listener: Listener): () => void {
    let set = this.listeners.get(strike);
    if (!set) {
      set = new Set();
      this.listeners.set(strike, set);
    }
    set.add(listener);
    return () => set.delete(listener);
  }

  /** Fan-out point called from services/socket.ts for every inbound message. */
  ingest(message: ServerMessage): void {
    const now = Date.now();
    if (message.type === "snapshot") {
      for (const row of message.rows) {
        if (row.straddle != null) this.recordTick(row.strike, row.straddle, now);
      }
    } else if (message.type === "row_update") {
      if (message.row.straddle != null) this.recordTick(message.row.strike, message.row.straddle, now);
    }
  }

  private recordTick(strike: number, value: number, timestamp: number): void {
    let buffer = this.buffers.get(strike);
    if (!buffer) {
      buffer = [];
      this.buffers.set(strike, buffer);
    }
    buffer.push({ timestamp, value });

    const cutoff = timestamp - ROLLING_WINDOW_MS;
    let evictCount = 0;
    while (evictCount < buffer.length && buffer[evictCount].timestamp < cutoff) evictCount += 1;
    if (evictCount > 0) buffer.splice(0, evictCount);

    if (hasIndexedDb) this.writeQueue.push({ strike, timestamp, value });

    this.versions.set(strike, this.getVersion(strike) + 1);
    for (const listener of this.listeners.get(strike) ?? []) listener();
  }

  private openDb(): Promise<IDBDatabase> {
    if (this.dbPromise) return this.dbPromise;
    this.dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: "id", autoIncrement: true });
          store.createIndex("timestamp", "timestamp");
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return this.dbPromise;
  }

  /** Hydrates every strike's in-memory buffer from IndexedDB on startup, so a
   * page refresh doesn't lose the current rolling window of history. */
  private async hydrateAll(db: IDBDatabase): Promise<void> {
    const cutoff = Date.now() - ROLLING_WINDOW_MS;
    const tx = db.transaction(STORE_NAME, "readonly");
    const index = tx.objectStore(STORE_NAME).index("timestamp");
    const range = IDBKeyRange.lowerBound(cutoff);
    const loaded = new Map<number, Tick[]>();

    await new Promise<void>((resolve, reject) => {
      const cursorRequest = index.openCursor(range);
      cursorRequest.onsuccess = () => {
        const cursor = cursorRequest.result;
        if (!cursor) {
          resolve();
          return;
        }
        const record = cursor.value as StoredTick;
        let arr = loaded.get(record.strike);
        if (!arr) {
          arr = [];
          loaded.set(record.strike, arr);
        }
        arr.push({ timestamp: record.timestamp, value: record.value });
        cursor.continue();
      };
      cursorRequest.onerror = () => reject(cursorRequest.error as unknown);
    });

    for (const [strike, ticks] of loaded) {
      ticks.sort((a, b) => a.timestamp - b.timestamp);
      this.buffers.set(strike, ticks);
      this.versions.set(strike, this.getVersion(strike) + 1);
      for (const listener of this.listeners.get(strike) ?? []) listener();
    }
  }

  private async flush(): Promise<void> {
    if (this.writeQueue.length === 0) return;
    const batch = this.writeQueue;
    this.writeQueue = [];
    try {
      const db = await this.openDb();
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      for (const record of batch) store.add(record);
      await new Promise<void>((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error as unknown);
      });
    } catch (err) {
      console.error("tickStore: failed to flush ticks to IndexedDB", err);
    }
  }

  /** Periodic range-delete of ticks older than the rolling window, using the
   * timestamp index instead of reading every record back into memory. */
  private async evictOld(): Promise<void> {
    const cutoff = Date.now() - ROLLING_WINDOW_MS;
    try {
      const db = await this.openDb();
      const tx = db.transaction(STORE_NAME, "readwrite");
      const index = tx.objectStore(STORE_NAME).index("timestamp");
      const range = IDBKeyRange.upperBound(cutoff, true);
      await new Promise<void>((resolve, reject) => {
        const cursorRequest = index.openCursor(range);
        cursorRequest.onsuccess = () => {
          const cursor = cursorRequest.result;
          if (!cursor) {
            resolve();
            return;
          }
          cursor.delete();
          cursor.continue();
        };
        cursorRequest.onerror = () => reject(cursorRequest.error as unknown);
      });
    } catch (err) {
      console.error("tickStore: failed to evict old ticks from IndexedDB", err);
    }
  }
}

export const tickStore = new TickStore();
