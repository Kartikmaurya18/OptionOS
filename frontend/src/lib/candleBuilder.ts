// Pure OHLC bucketing logic. No side effects, no imports from tickStore/UI --
// this is intentionally standalone so it can be reused for Call/Put candles
// later and tested in isolation from the WebSocket/React code.

export type Timeframe = "1m" | "5m" | "15m" | "1h";

export interface Tick {
  timestamp: number; // epoch ms
  value: number;
}

export interface Candle {
  time: number; // epoch ms, start of the bucket
  open: number;
  high: number;
  low: number;
  close: number;
  tickCount: number; // ticks observed in this bucket; proxy for activity/"volume"
}

const TIMEFRAME_MS: Record<Timeframe, number> = {
  "1m": 60_000,
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
};

/** Floors a timestamp to the start of its bucket, aligned to clock time (e.g.
 * 1m buckets start exactly at :00 seconds, not at the first tick received). */
function bucketStart(timestamp: number, bucketMs: number): number {
  return Math.floor(timestamp / bucketMs) * bucketMs;
}

/**
 * Buckets ticks into fixed, clock-aligned time windows and computes OHLC per
 * bucket.
 *
 * Steps:
 * 1. Sort ticks by timestamp (defensive copy -- the input array is never
 *    mutated, keeping this function side-effect free).
 * 2. Group ticks into buckets keyed by their clock-aligned bucket start time.
 * 3. Walk every bucket from the first to the last tick's bucket, in order,
 *    with no gaps skipped.
 * 4. For a bucket that has ticks: open = first tick's value, close = last
 *    tick's value, high/low = max/min across the bucket's ticks.
 * 5. For a bucket with no ticks (WebSocket silent for that strike in that
 *    window): carry the previous bucket's close forward as a flat candle
 *    (open = high = low = close = previous close, tickCount = 0). This keeps
 *    the series gap-free -- see the "why carry-forward" note in the plan --
 *    the same approach TradingView/Zerodha-style charts use for illiquid
 *    instruments so a quiet strike doesn't look like a broken feed.
 */
export function buildCandles(ticks: Tick[], timeframe: Timeframe): Candle[] {
  if (ticks.length === 0) return [];

  const bucketMs = TIMEFRAME_MS[timeframe];
  const sorted = [...ticks].sort((a, b) => a.timestamp - b.timestamp);

  const buckets = new Map<number, Tick[]>();
  for (const tick of sorted) {
    const start = bucketStart(tick.timestamp, bucketMs);
    let bucket = buckets.get(start);
    if (!bucket) {
      bucket = [];
      buckets.set(start, bucket);
    }
    bucket.push(tick);
  }

  const firstBucket = bucketStart(sorted[0].timestamp, bucketMs);
  const lastBucket = bucketStart(sorted[sorted.length - 1].timestamp, bucketMs);

  const candles: Candle[] = [];
  let previousClose = sorted[0].value;

  for (let time = firstBucket; time <= lastBucket; time += bucketMs) {
    const bucketTicks = buckets.get(time);

    if (bucketTicks && bucketTicks.length > 0) {
      let high = bucketTicks[0].value;
      let low = bucketTicks[0].value;
      for (const tick of bucketTicks) {
        if (tick.value > high) high = tick.value;
        if (tick.value < low) low = tick.value;
      }
      const open = bucketTicks[0].value;
      const close = bucketTicks[bucketTicks.length - 1].value;

      candles.push({ time, open, high, low, close, tickCount: bucketTicks.length });
      previousClose = close;
    } else {
      candles.push({
        time,
        open: previousClose,
        high: previousClose,
        low: previousClose,
        close: previousClose,
        tickCount: 0,
      });
    }
  }

  return candles;
}

/**
 * Merges server-backfilled historical candles with the live, tick-derived
 * series for the same instrument/timeframe. The live series (from
 * useStraddleCandles/tickStore) covers everything since this tab
 * connected; historical candles (from useCandleBackfill, served out of
 * ClickHouse) fill in everything before that.
 *
 * Historical candles at or after the live series' first bucket are
 * dropped rather than merged/overlapped -- the live series is always the
 * source of truth for any bucket it covers, since it reflects this
 * session's actual ticks, not a persisted (and possibly-still-forming)
 * approximation of the same bucket.
 */
export function mergeCandleSeries(historical: Candle[], live: Candle[]): Candle[] {
  if (live.length === 0) return historical;
  const liveStart = live[0].time;
  const older = historical.filter((candle) => candle.time < liveStart);
  return [...older, ...live];
}
