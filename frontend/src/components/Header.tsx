import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { useAssets } from "@/hooks/useAssets";
import { useHeaderStats } from "@/hooks/useHeaderStats";
import { switchAsset } from "@/services/socket";
import { cn } from "@/lib/utils";
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

function AssetSwitcher({ current }: { current: string }) {
  const assets = useAssets();
  if (assets.length <= 1) return null;

  return (
    <div className="flex items-center gap-1 rounded-md border border-border bg-surface-raised p-0.5">
      {assets.map((asset) => (
        <button
          key={asset}
          type="button"
          onClick={() => switchAsset(asset)}
          disabled={asset === current}
          className={cn(
            "rounded px-2.5 py-1 text-xs font-semibold tracking-wide transition-colors",
            asset === current ? "bg-surface text-accent" : "text-muted hover:text-foreground",
          )}
        >
          {asset}
        </button>
      ))}
    </div>
  );
}

export function Header() {
  const stats = useHeaderStats();
  useTick(1000); // re-render every second so "last updated Xs ago" stays fresh

  return (
    <header className="sticky top-0 z-20 flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-border bg-surface px-6 py-4">
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold tracking-wide text-foreground">
          {stats.asset} Options Straddle
          <AssetSwitcher current={stats.asset} />
        </div>
        <div className="text-xs text-muted">Live via Delta Exchange</div>
      </div>

      <Stat label={`${stats.asset} Spot`} value={stats.spotPrice != null ? `$${formatPrice(stats.spotPrice)}` : "--"} />
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
