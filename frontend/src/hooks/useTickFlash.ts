import { useEffect, useRef, useState } from "react";

export type FlashDirection = "up" | "down";

export interface Flash {
  direction: FlashDirection;
  // Unique per occurrence (not just per value) so two consecutive changes
  // in the same direction each still mount a fresh animation element --
  // see FlashValue, which keys off this to force a remount rather than
  // trying to restart a CSS animation on an already-mounted node.
  nonce: number;
}

/** Pure decision logic, kept separate from the React glue below so it's
 * testable without a DOM: no flash on the first render (prev == null), no
 * flash on a no-op update, "up" if the value increased, "down" if it
 * decreased. */
export function flashDirection(prev: number | null | undefined, next: number | null | undefined): FlashDirection | null {
  if (prev == null || next == null || next === prev) return null;
  return next > prev ? "up" : "down";
}

/** Detects when `value` genuinely changes and returns a one-shot Flash
 * descriptor for the caller to render a self-clearing animation from. */
export function useTickFlash(value: number | null | undefined): Flash | null {
  const prevRef = useRef(value);
  const [flash, setFlash] = useState<Flash | null>(null);

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = value;
    const direction = flashDirection(prev, value);
    if (direction) setFlash({ direction, nonce: Date.now() + Math.random() });
  }, [value]);

  return flash;
}
