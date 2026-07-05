import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { optionStore } from "@/services/optionStore";
import type { SortColumn, SortDirection } from "@/types/options";

// Value-based sorts (Call/Put/Straddle) are recomputed on this interval
// instead of on every tick -- otherwise a single price update could
// reshuffle row order dozens of times a second, which is worse for
// readability than the "no full table refresh" problem this dashboard
// exists to solve. Strike-sort has no such issue (strikes never change) so
// it's applied immediately.
const VALUE_SORT_INTERVAL_MS = 400;

function sortStrikes(strikes: number[], column: SortColumn, direction: SortDirection): number[] {
  const factor = direction === "asc" ? 1 : -1;
  const sorted = [...strikes];
  sorted.sort((a, b) => {
    if (column === "strike") return (a - b) * factor;

    const rowA = optionStore.getRow(a);
    const rowB = optionStore.getRow(b);
    const valueA = column === "call" ? rowA?.callLtp : column === "put" ? rowA?.putLtp : rowA?.straddle;
    const valueB = column === "call" ? rowB?.callLtp : column === "put" ? rowB?.putLtp : rowB?.straddle;

    if (valueA == null && valueB == null) return 0;
    if (valueA == null) return 1;
    if (valueB == null) return -1;
    return (valueA - valueB) * factor;
  });
  return sorted;
}

function sameOrder(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

/** Returns the strikes to render, in order, given the current search term
 * and sort settings. */
export function useStrikeList(searchTerm: string, sortColumn: SortColumn, sortDirection: SortDirection): number[] {
  const allStrikes = useSyncExternalStore(
    (listener) => optionStore.subscribeStrikes(listener),
    () => optionStore.getStrikes(),
  );

  const filtered = useMemo(() => {
    const trimmed = searchTerm.trim();
    if (!trimmed) return allStrikes;
    return allStrikes.filter((strike) => strike.toString().includes(trimmed));
  }, [allStrikes, searchTerm]);

  const [ordered, setOrdered] = useState<number[]>(() => sortStrikes(filtered, sortColumn, sortDirection));

  useEffect(() => {
    setOrdered(sortStrikes(filtered, sortColumn, sortDirection));

    if (sortColumn === "strike") return;

    const interval = setInterval(() => {
      setOrdered((prev) => {
        const next = sortStrikes(filtered, sortColumn, sortDirection);
        return sameOrder(prev, next) ? prev : next;
      });
    }, VALUE_SORT_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [filtered, sortColumn, sortDirection]);

  return ordered;
}
