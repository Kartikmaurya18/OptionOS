import { useState } from "react";

import { Header } from "@/components/Header";
import { OptionsTable } from "@/components/OptionsTable";
import { SearchBox } from "@/components/SearchBox";
import { StraddleChart } from "@/components/StraddleChart";
import { cn } from "@/lib/utils";
import { useStrikeList } from "@/hooks/useStrikeList";
import type { SortColumn, SortDirection } from "@/types/options";

type Tab = "table" | "chart";

const TABS: Array<{ key: Tab; label: string }> = [
  { key: "table", label: "Options Table" },
  { key: "chart", label: "Straddle Chart" },
];

export function Dashboard() {
  const [tab, setTab] = useState<Tab>("table");
  const [searchTerm, setSearchTerm] = useState("");
  const [sortColumn, setSortColumn] = useState<SortColumn>("strike");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const strikes = useStrikeList(searchTerm, sortColumn, sortDirection);

  function handleSort(column: SortColumn): void {
    if (column === sortColumn) {
      setSortDirection((direction) => (direction === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(column);
      setSortDirection("asc");
    }
  }

  return (
    <div className="flex h-full flex-col">
      <Header />
      <main className="flex flex-1 flex-col gap-4 overflow-hidden p-6">
        <div className="flex gap-1 border-b border-border">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={cn(
                "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                tab === key
                  ? "border-accent text-foreground"
                  : "border-transparent text-muted hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "table" ? (
          <>
            <SearchBox value={searchTerm} onChange={setSearchTerm} />
            <OptionsTable strikes={strikes} sortColumn={sortColumn} sortDirection={sortDirection} onSort={handleSort} />
          </>
        ) : (
          <StraddleChart />
        )}
      </main>
    </div>
  );
}
