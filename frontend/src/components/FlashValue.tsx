import { ArrowDown, ArrowUp } from "lucide-react";

import { useTickFlash } from "@/hooks/useTickFlash";
import { cn } from "@/lib/utils";

interface FlashValueProps {
  value: number | null | undefined;
  format: (value: number | null | undefined) => string;
  className?: string;
}

/** Renders a formatted number that briefly flashes green/red and shows a
 * directional arrow whenever it actually changes -- the difference between
 * a data table and something that reads as live market data. Reused by
 * OptionTableRow (call/put/straddle) and Header (spot price) so all four
 * ticking numbers in the app behave identically. */
export function FlashValue({ value, format, className }: FlashValueProps) {
  const flash = useTickFlash(value);

  return (
    <span className={cn("relative inline-flex items-center gap-1", className)}>
      {flash && (
        <span
          key={flash.nonce}
          aria-hidden
          className={cn(
            "pointer-events-none absolute -inset-x-2 -inset-y-1 -z-10 rounded",
            flash.direction === "up" ? "animate-flash-up" : "animate-flash-down",
          )}
        />
      )}
      {format(value)}
      {flash &&
        (flash.direction === "up" ? (
          <ArrowUp key={`arrow-${flash.nonce}`} aria-hidden className="h-3 w-3 text-call animate-arrow-fade" />
        ) : (
          <ArrowDown key={`arrow-${flash.nonce}`} aria-hidden className="h-3 w-3 text-put animate-arrow-fade" />
        ))}
    </span>
  );
}
