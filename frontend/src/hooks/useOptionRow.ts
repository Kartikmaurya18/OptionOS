import { useSyncExternalStore } from "react";

import { optionStore } from "@/services/optionStore";
import type { OptionRow } from "@/types/options";

/** Subscribes to a single strike's row. React only re-renders the
 * component calling this when that exact strike changes. */
export function useOptionRow(strike: number): OptionRow | undefined {
  return useSyncExternalStore(
    (listener) => optionStore.subscribeRow(strike, listener),
    () => optionStore.getRow(strike),
  );
}
