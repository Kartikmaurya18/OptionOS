import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

import { OptionTableRow } from "@/components/OptionTableRow";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { SortColumn, SortDirection } from "@/types/options";

interface OptionsTableProps {
  strikes: number[];
  sortColumn: SortColumn;
  sortDirection: SortDirection;
  onSort: (column: SortColumn) => void;
}

const ROW_HEIGHT = 44;

const COLUMNS: Array<{ key: SortColumn; label: string; className?: string }> = [
  { key: "call", label: "Call LTP", className: "text-call" },
  { key: "put", label: "Put LTP", className: "text-put" },
  { key: "strike", label: "Strike" },
  { key: "straddle", label: "Straddle", className: "text-straddle" },
];

function SortIcon({ active, direction }: { active: boolean; direction: SortDirection }) {
  if (!active) return <ArrowUpDown className="h-3.5 w-3.5 opacity-40" />;
  return direction === "asc" ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />;
}

export function OptionsTable({ strikes, sortColumn, sortDirection, onSort }: OptionsTableProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: strikes.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });

  const virtualItems = virtualizer.getVirtualItems();

  return (
    <div ref={scrollRef} className="relative flex-1 overflow-auto rounded-lg border border-border bg-surface">
      <Table>
        <TableHeader>
          <TableRow className="border-b-0 hover:bg-transparent">
            {COLUMNS.map((column) => (
              <TableHead key={column.key}>
                <button
                  type="button"
                  onClick={() => onSort(column.key)}
                  className={cn("flex items-center gap-1.5 hover:text-foreground", column.className)}
                >
                  {column.label}
                  <SortIcon active={sortColumn === column.key} direction={sortDirection} />
                </button>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>

        <TableBody style={{ height: virtualizer.getTotalSize() }}>
          {strikes.length === 0 ? (
            <div role="row" className="px-4 py-10 text-center text-sm text-muted">
              No strikes to display.
            </div>
          ) : (
            virtualItems.map((virtualRow) => (
              <OptionTableRow
                key={virtualRow.key}
                strike={strikes[virtualRow.index]}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              />
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
