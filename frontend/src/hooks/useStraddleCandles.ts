import { useRef, useSyncExternalStore } from "react";

import { buildCandles, type Candle, type Timeframe } from "@/lib/candleBuilder";
import { tickStore } from "@/lib/tickStore";

interface Cache {
  strike: number;
  timeframe: Timeframe;
  version: number;
  candles: Candle[];
}

/** Straddle candles for one strike/timeframe, recomputed only when new ticks
 * arrive for that strike. `tickStore.getVersion` (bumped once per tick) lets
 * us return the same array reference across renders when nothing changed --
 * useSyncExternalStore requires that stability, otherwise a fresh array on
 * every call would look like a permanent "changed" snapshot and trip its
 * tearing check. */
export function useStraddleCandles(strike: number, timeframe: Timeframe): Candle[] {
  const cacheRef = useRef<Cache | null>(null);

  return useSyncExternalStore(
    (listener) => tickStore.subscribe(strike, listener),
    () => {
      const version = tickStore.getVersion(strike);
      const cached = cacheRef.current;
      if (cached && cached.strike === strike && cached.timeframe === timeframe && cached.version === version) {
        return cached.candles;
      }

      const candles = buildCandles(tickStore.getTicks(strike), timeframe);
      cacheRef.current = { strike, timeframe, version, candles };
      return candles;
    },
  );
}
