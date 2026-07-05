import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { useHeaderStats } from "@/hooks/useHeaderStats";
import { formatExpiry, formatPrice, formatRelativeTime } from "@/utils/format";

function useTick(intervalMs: number): void {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className="text-lg font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  );
}

export function Header() {
  const stats = useHeaderStats();
  useTick(1000); // re-render every second so "last updated Xs ago" stays fresh

  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-border bg-surface px-6 py-4">
      <div>
        <div className="text-sm font-semibold tracking-wide text-foreground">BTC Options Straddle</div>
        <div className="text-xs text-muted">Live via Delta Exchange</div>
      </div>

      <Stat label="BTC Spot" value={stats.spotPrice != null ? `$${formatPrice(stats.spotPrice)}` : "--"} />
      <Stat label="Expiry" value={formatExpiry(stats.expiry)} />
      <Stat label="Strikes" value={String(stats.strikeCount)} />
      <Stat label="Last Update" value={formatRelativeTime(stats.lastMessageTime)} />

      <div className="ml-auto flex flex-col items-end gap-1.5">
        <div className="text-xs font-medium uppercase tracking-wide text-muted">WebSocket</div>
        <StatusBadge phase={stats.phase} reconnectAttempts={stats.reconnectAttempts} />
      </div>
    </header>
  );
}
