import { useEffect, useState } from "react";

import { DEFAULT_ASSET } from "@/services/optionStore";

const DEFAULT_API_URL = `${window.location.protocol}//${window.location.hostname}:8000`;
const API_URL = import.meta.env.VITE_API_URL || DEFAULT_API_URL;

/** Which asset shards the connected backend is actually running -- avoids
 * hardcoding the list in the UI, so adding a third asset server-side (say,
 * SOL) doesn't require a frontend deploy just to expose the switcher. */
export function useAssets(): string[] {
  const [assets, setAssets] = useState<string[]>([DEFAULT_ASSET]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/api/assets`)
      .then((res) => res.json() as Promise<{ assets: string[] }>)
      .then((data) => {
        if (!cancelled && Array.isArray(data.assets) && data.assets.length > 0) setAssets(data.assets);
      })
      .catch(() => {
        // backend unreachable at mount time -- keep the single-asset default,
        // the WS connection's own reconnect logic will surface the outage
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return assets;
}
