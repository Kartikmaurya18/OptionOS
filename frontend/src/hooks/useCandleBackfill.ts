import { useEffect, useState } from "react";

import type { Candle, Timeframe } from "@/lib/candleBuilder";

const DEFAULT_API_URL = `${window.location.protocol}//${window.location.hostname}:8000`;
const API_URL = import.meta.env.VITE_API_URL || DEFAULT_API_URL;

// Matches tickStore's ROLLING_WINDOW_MS -- there's no point backfilling
// further back than the live in-memory/IndexedDB path already tries to
// cover once it has ticks again.
const BACKFILL_WINDOW_MS = 24 * 60 * 60 * 1000;

interface CandlesResponse {
  candles: Candle[];
}

/** Fetches closed historical candles for one instrument/timeframe from
 * HistoricalBackfillService, once on mount and again whenever the asset,
 * strike, or timeframe changes -- so switching strikes or timeframes in
 * the chart re-backfills instead of showing only whatever ticks happened
 * to arrive live since the switch. */
export function useCandleBackfill(asset: string, strike: number, timeframe: Timeframe): Candle[] {
  const [candles, setCandles] = useState<Candle[]>([]);

  useEffect(() => {
    if (strike < 0) {
      setCandles([]);
      return;
    }

    let cancelled = false;
    const to = Date.now();
    const from = to - BACKFILL_WINDOW_MS;
    const params = new URLSearchParams({
      asset,
      strike: String(strike),
      timeframe,
      from: String(from),
      to: String(to),
    });

    fetch(`${API_URL}/api/candles?${params.toString()}`)
      .then((res) => res.json() as Promise<CandlesResponse>)
      .then((data) => {
        if (!cancelled) setCandles(Array.isArray(data.candles) ? data.candles : []);
      })
      .catch((err: unknown) => {
        console.error("useCandleBackfill: failed to fetch candle history", err);
        if (!cancelled) setCandles([]);
      });

    return () => {
      cancelled = true;
    };
  }, [asset, strike, timeframe]);

  return candles;
}
