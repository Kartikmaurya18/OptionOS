import { useSyncExternalStore } from "react";

import { optionStore } from "@/services/optionStore";
import type { HeaderStats } from "@/types/options";

export function useHeaderStats(): HeaderStats {
  return useSyncExternalStore(
    (listener) => optionStore.subscribeHeaderStats(listener),
    () => optionStore.getHeaderStats(),
  );
}
