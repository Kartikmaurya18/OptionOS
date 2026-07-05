import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

// Div-based (not real <table>/<tr>) so the virtualized body can position
// rows with `transform` -- real <tr> elements don't support absolute
// positioning reliably across browsers. ARIA table roles keep it
// accessible. Header and body rows share the same grid-template-columns
// so cells line up.

const GRID_COLUMNS = "grid-cols-[1fr_1fr_1fr_1fr]";

function Table({ className, ...props }: ComponentProps<"div">) {
  return <div role="table" className={cn("w-full text-sm", className)} {...props} />;
}

function TableHeader({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      role="rowgroup"
      className={cn("sticky top-0 z-10 border-b border-border bg-surface", className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: ComponentProps<"div">) {
  return <div role="rowgroup" className={cn("relative", className)} {...props} />;
}

function TableRow({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      role="row"
      className={cn(
        "grid items-center border-b border-border/60 transition-colors hover:bg-surface-raised/60",
        GRID_COLUMNS,
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      role="columnheader"
      className={cn(
        "select-none px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: ComponentProps<"div">) {
  return <div role="cell" className={cn("px-4 py-2.5 tabular-nums", className)} {...props} />;
}

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell };
