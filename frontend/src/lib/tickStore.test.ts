import { describe, expect, it } from "vitest";

import { tickStore } from "@/lib/tickStore";
import type { RowUpdateMessage, SnapshotMessage } from "@/types/options";

// Node test environment has no IndexedDB, so tickStore automatically skips
// persistence and runs purely in-memory here -- this verifies the ingest/
// eviction logic in isolation, same as the plan's "console.log/simple test
// before touching the UI" step.

function row(strike: number, straddle: number | null) {
  return {
    strike,
    callSymbol: `C-${strike}`,
    putSymbol: `P-${strike}`,
    callLtp: straddle,
    putLtp: straddle,
    straddle,
    lastUpdated: Date.now(),
  };
}

describe("tickStore", () => {
  it("records a tick per strike from a snapshot, skipping null straddles", () => {
    const snapshot: SnapshotMessage = {
      type: "snapshot",
      asset: "BTC",
      expiry: "050726",
      spotPrice: 50000,
      rows: [row(100000, 250.5), row(105000, null)],
    };

    tickStore.ingest(snapshot);

    expect(tickStore.getTicks(100000)).toHaveLength(1);
    expect(tickStore.getTicks(100000)[0].value).toBe(250.5);
    expect(tickStore.getTicks(105000)).toHaveLength(0);
  });

  it("records a tick from a row_update and bumps the version", () => {
    const before = tickStore.getVersion(100000);

    const update: RowUpdateMessage = {
      type: "row_update",
      asset: "BTC",
      updatedField: "call",
      row: row(100000, 260),
    };
    tickStore.ingest(update);

    expect(tickStore.getVersion(100000)).toBe(before + 1);
    const ticks = tickStore.getTicks(100000);
    expect(ticks[ticks.length - 1].value).toBe(260);
  });

  it("notifies subscribers on new ticks for that strike only", () => {
    let notifiedA = 0;
    let notifiedB = 0;
    const unsubA = tickStore.subscribe(200000, () => (notifiedA += 1));
    const unsubB = tickStore.subscribe(300000, () => (notifiedB += 1));

    tickStore.ingest({ type: "row_update", asset: "BTC", updatedField: "put", row: row(200000, 10) });

    expect(notifiedA).toBe(1);
    expect(notifiedB).toBe(0);

    unsubA();
    unsubB();
  });
});
