import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { ConnectionPhase } from "@/types/options";

interface StatusBadgeProps {
  phase: ConnectionPhase;
  reconnectAttempts: number;
}

const LABELS: Record<ConnectionPhase, string> = {
  connected: "Connected",
  disconnected: "Disconnected",
  connecting: "Connecting",
};

const VARIANTS: Record<ConnectionPhase, "positive" | "negative" | "warning"> = {
  connected: "positive",
  disconnected: "negative",
  connecting: "warning",
};

const DOT_COLORS: Record<ConnectionPhase, string> = {
  connected: "bg-positive",
  disconnected: "bg-negative",
  connecting: "bg-warning",
};

export function StatusBadge({ phase, reconnectAttempts }: StatusBadgeProps) {
  return (
    <Badge variant={VARIANTS[phase]}>
      <span className="relative flex h-1.5 w-1.5">
        {/* Radiating ring only while genuinely connected -- a "live" pulse
            on a connecting/disconnected state would say the opposite of
            what's true. */}
        {phase === "connected" && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-75", DOT_COLORS[phase])} />
        )}
        <span
          className={cn(
            "relative inline-flex h-1.5 w-1.5 rounded-full",
            DOT_COLORS[phase],
            phase === "connecting" && "animate-pulse",
          )}
        />
      </span>
      {LABELS[phase]}
      {phase === "disconnected" && reconnectAttempts > 0 ? ` (attempt ${reconnectAttempts})` : ""}
    </Badge>
  );
}
