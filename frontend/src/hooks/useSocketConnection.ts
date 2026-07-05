import { useEffect } from "react";

import { connectOptionsSocket } from "@/services/socket";

/** Mounted once at the app root: opens the backend WebSocket and tears it
 * down on unmount. */
export function useSocketConnection(): void {
  useEffect(() => connectOptionsSocket(), []);
}
