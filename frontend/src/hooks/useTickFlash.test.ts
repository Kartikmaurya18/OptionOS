import { describe, expect, it } from "vitest";

import { flashDirection } from "@/hooks/useTickFlash";

describe("flashDirection", () => {
  it("returns null on the first value (no previous to compare against)", () => {
    expect(flashDirection(null, 100)).toBeNull();
    expect(flashDirection(undefined, 100)).toBeNull();
  });

  it("returns null when the value is unchanged", () => {
    expect(flashDirection(100, 100)).toBeNull();
  });

  it("returns null when the new value is null/undefined (nothing to flash)", () => {
    expect(flashDirection(100, null)).toBeNull();
    expect(flashDirection(100, undefined)).toBeNull();
  });

  it("returns 'up' when the value increased", () => {
    expect(flashDirection(100, 105)).toBe("up");
  });

  it("returns 'down' when the value decreased", () => {
    expect(flashDirection(100, 95)).toBe("down");
  });
});
