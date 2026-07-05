import { describe, expect, it } from "vitest";

import { buildCandles, type Tick } from "@/lib/candleBuilder";

const M = 60_000; // 1 minute in ms
// Pick a base that's already minute-aligned so bucket math is easy to reason about.
const BASE = Math.floor(Date.now() / M) * M;

function tick(minuteOffset: number, secondOffset: number, value: number): Tick {
  return { timestamp: BASE + minuteOffset * M + secondOffset * 1000, value };
}

describe("buildCandles", () => {
  it("returns an empty array for no ticks", () => {
    expect(buildCandles([], "1m")).toEqual([]);
  });

  it("computes open/high/low/close/tickCount for a single bucket", () => {
    const ticks = [tick(0, 0, 100), tick(0, 10, 105), tick(0, 20, 95), tick(0, 30, 102)];
    const candles = buildCandles(ticks, "1m");

    expect(candles).toEqual([{ time: BASE, open: 100, high: 105, low: 95, close: 102, tickCount: 4 }]);
  });

  it("handles a single tick as a flat candle", () => {
    const candles = buildCandles([tick(0, 0, 100)], "1m");
    expect(candles).toEqual([{ time: BASE, open: 100, high: 100, low: 100, close: 100, tickCount: 1 }]);
  });

  it("buckets are clock-aligned regardless of the first tick's offset within the minute", () => {
    const candles = buildCandles([tick(0, 45, 100)], "1m");
    // Bucket start is the top of the minute, not the moment the first tick arrived.
    expect(candles[0].time).toBe(BASE);
  });

  it("splits ticks across multiple buckets in order", () => {
    const ticks = [tick(0, 0, 100), tick(0, 30, 110), tick(1, 0, 120), tick(1, 45, 90)];
    const candles = buildCandles(ticks, "1m");

    expect(candles).toEqual([
      { time: BASE, open: 100, high: 110, low: 100, close: 110, tickCount: 2 },
      { time: BASE + M, open: 120, high: 120, low: 90, close: 90, tickCount: 2 },
    ]);
  });

  it("carries the previous close forward as a flat candle through empty buckets", () => {
    // Ticks in minute 0 and minute 3, nothing in between -- minutes 1 and 2
    // should appear as flat candles at minute 0's close.
    const ticks = [tick(0, 0, 100), tick(0, 30, 108), tick(3, 0, 130)];
    const candles = buildCandles(ticks, "1m");

    expect(candles).toHaveLength(4);
    expect(candles[0]).toEqual({ time: BASE, open: 100, high: 108, low: 100, close: 108, tickCount: 2 });
    expect(candles[1]).toEqual({ time: BASE + M, open: 108, high: 108, low: 108, close: 108, tickCount: 0 });
    expect(candles[2]).toEqual({ time: BASE + 2 * M, open: 108, high: 108, low: 108, close: 108, tickCount: 0 });
    expect(candles[3]).toEqual({ time: BASE + 3 * M, open: 130, high: 130, low: 130, close: 130, tickCount: 1 });
  });

  it("sorts out-of-order ticks without mutating the input array", () => {
    const ticks = [tick(0, 30, 110), tick(0, 0, 100)];
    const original = [...ticks];

    const candles = buildCandles(ticks, "1m");

    expect(candles[0]).toEqual({ time: BASE, open: 100, high: 110, low: 100, close: 110, tickCount: 2 });
    expect(ticks).toEqual(original); // no side effects on the input
  });

  it("uses the requested timeframe's bucket size", () => {
    const fiveMin = 5 * M;
    const alignedBase = Math.floor(BASE / fiveMin) * fiveMin;
    const ticks = [
      { timestamp: alignedBase, value: 100 },
      { timestamp: alignedBase + 4 * M + 59_000, value: 150 },
      { timestamp: alignedBase + fiveMin, value: 160 },
    ];
    const candles = buildCandles(ticks, "5m");

    expect(candles).toHaveLength(2);
    expect(candles[0]).toEqual({ time: alignedBase, open: 100, high: 150, low: 100, close: 150, tickCount: 2 });
    expect(candles[1]).toEqual({
      time: alignedBase + fiveMin,
      open: 160,
      high: 160,
      low: 160,
      close: 160,
      tickCount: 1,
    });
  });
});
