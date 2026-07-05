import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  createChart,
  CrosshairMode,
  type CandlestickData,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import { Button } from "@/components/ui/button";
import { useOptionRow } from "@/hooks/useOptionRow";
import { useStraddleCandles } from "@/hooks/useStraddleCandles";
import { useStrikeList } from "@/hooks/useStrikeList";
import type { Candle, Timeframe } from "@/lib/candleBuilder";
import { cn } from "@/lib/utils";
import { formatPrice, formatStrike } from "@/utils/format";

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h"];

interface Ohlc {
  open: number;
  high: number;
  low: number;
  close: number;
}

function toChartCandle(candle: Candle): CandlestickData<Time> {
  return {
    // lightweight-charts' numeric Time (UTCTimestamp) is seconds, our Candle.time is ms.
    time: Math.floor(candle.time / 1000) as UTCTimestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  };
}

/** Reads a color straight from the app's CSS theme instead of duplicating
 * hex literals here -- lightweight-charts draws to canvas, so it can't pick
 * up CSS custom properties on its own, but we can read them once and hand
 * over the resolved value. */
function themeColor(variable: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
  return value || fallback;
}

export function StraddleChart() {
  const strikes = useStrikeList("", "strike", "asc");
  const [strike, setStrike] = useState<number | null>(null);
  const [timeframe, setTimeframe] = useState<Timeframe>("1m");

  useEffect(() => {
    if (strikes.length === 0) return;
    if (strike == null || !strikes.includes(strike)) setStrike(strikes[0]);
  }, [strikes, strike]);

  const row = useOptionRow(strike ?? -1);
  const candles = useStraddleCandles(strike ?? -1, timeframe);

  const containerRef = useRef<HTMLDivElement>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [hover, setHover] = useState<Ohlc | null>(null);

  // Chart lifecycle: created once on mount, torn down on unmount. Data and
  // theming are applied in separate effects below so switching strike/
  // timeframe or theme colors never requires recreating the chart.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: {
        background: { color: "transparent" },
        textColor: themeColor("--color-muted", "#6b7688"),
        fontFamily:
          "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
      },
      grid: {
        vertLines: { color: themeColor("--color-border", "#232a36") },
        horzLines: { color: themeColor("--color-border", "#232a36") },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: themeColor("--color-border", "#232a36") },
      timeScale: {
        borderColor: themeColor("--color-border", "#232a36"),
        timeVisible: true,
        secondsVisible: false,
      },
      width: container.clientWidth,
      height: container.clientHeight,
    });

    const upColor = themeColor("--color-positive", "#22c55e");
    const downColor = themeColor("--color-negative", "#f87171");

    const series = chart.addSeries(CandlestickSeries, {
      upColor,
      downColor,
      borderUpColor: upColor,
      borderDownColor: downColor,
      wickUpColor: upColor,
      wickDownColor: downColor,
    });
    seriesRef.current = series;

    chart.subscribeCrosshairMove((param: MouseEventParams<Time>) => {
      const point = param.seriesData.get(series);
      if (!point || !("open" in point)) {
        setHover(null);
        return;
      }
      setHover({ open: point.open, high: point.high, low: point.low, close: point.close });
    });

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      chart.resize(entry.contentRect.width, entry.contentRect.height);
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      seriesRef.current = null;
    };
  }, []);

  // Live updates: pushes the full candle series (small: at most 1440 bars
  // for 1m/24h) every time a new tick arrives for the open strike, which
  // naturally updates the still-forming last bar without a chart reload.
  useEffect(() => {
    seriesRef.current?.setData(candles.map(toChartCandle));
  }, [candles]);

  const latest = candles[candles.length - 1];
  const legend =
    hover ?? (latest ? { open: latest.open, high: latest.high, low: latest.low, close: latest.close } : null);

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-lg border border-border bg-surface px-4 py-3">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted">Strike</div>
          <select
            value={strike ?? ""}
            onChange={(event) => setStrike(Number(event.target.value))}
            className="mt-1 h-8 rounded-md border border-border bg-surface-raised px-2 text-sm text-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent"
          >
            {strikes.map((s) => (
              <option key={s} value={s}>
                {formatStrike(s)}
              </option>
            ))}
          </select>
        </div>

        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted">Straddle</div>
          <div className="text-lg font-semibold tabular-nums text-straddle">{formatPrice(row?.straddle)}</div>
        </div>

        <div className="ml-auto flex items-center gap-1">
          {TIMEFRAMES.map((tf) => (
            <Button
              key={tf}
              type="button"
              size="sm"
              variant={tf === timeframe ? "default" : "ghost"}
              className={cn("h-8 w-auto px-3", tf === timeframe && "text-accent")}
              onClick={() => setTimeframe(tf)}
            >
              {tf}
            </Button>
          ))}
        </div>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-surface">
        {legend && (
          <div className="pointer-events-none absolute left-3 top-3 z-10 flex gap-3 rounded-md bg-surface-raised/90 px-3 py-1.5 text-xs tabular-nums text-foreground shadow">
            <span className="text-muted">
              O <span className="text-foreground">{formatPrice(legend.open)}</span>
            </span>
            <span className="text-muted">
              H <span className="text-call">{formatPrice(legend.high)}</span>
            </span>
            <span className="text-muted">
              L <span className="text-put">{formatPrice(legend.low)}</span>
            </span>
            <span className="text-muted">
              C <span className="text-foreground">{formatPrice(legend.close)}</span>
            </span>
          </div>
        )}
        <div ref={containerRef} className="h-full w-full" />
      </div>
    </div>
  );
}
