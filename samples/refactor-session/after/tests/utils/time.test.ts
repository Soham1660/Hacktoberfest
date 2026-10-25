import { describe, expect, it } from "vitest";
import { addDays, formatDate, formatTimestamp } from "../../src/utils/time";

const T = Date.UTC(2026, 9, 5, 7, 3);

describe("time helpers", () => {
  it("formats dates in UTC", () => {
    expect(formatDate(T)).toBe("2026-10-05");
  });

  it("formats timestamps in UTC", () => {
    expect(formatTimestamp(T)).toBe("2026-10-05 07:03 UTC");
  });

  it("adds whole days", () => {
    expect(formatDate(addDays(T, 30))).toBe("2026-11-04");
  });
});
