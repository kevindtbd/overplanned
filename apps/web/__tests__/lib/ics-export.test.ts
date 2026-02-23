/**
 * Tests for lib/ics-export.ts — pure function tests for .ics calendar generation.
 * Covers RFC 5545 compliance, escaping, CRLF line endings, time defaults, and edge cases.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { generateIcsCalendar, type IcsTripData, type IcsSlot } from "@/lib/ics-export";

// Freeze time so DTSTAMP is deterministic
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

function makeTrip(overrides: Partial<IcsTripData> = {}): IcsTripData {
  return {
    id: "trip-1",
    name: "Tokyo Trip",
    startDate: "2026-07-01",
    endDate: "2026-07-04",
    legs: [
      {
        city: "Tokyo",
        timezone: "Asia/Tokyo",
        startDate: "2026-07-01",
        endDate: "2026-07-04",
        dayOffset: 0,
      },
    ],
    slots: [],
    ...overrides,
  };
}

function makeSlot(overrides: Partial<IcsSlot> = {}): IcsSlot {
  return {
    id: "slot-1",
    dayNumber: 1,
    sortOrder: 1,
    startTime: null,
    endTime: null,
    durationMinutes: null,
    activityNode: {
      name: "Tsukiji Market",
      category: "dining",
    },
    ...overrides,
  };
}

describe("generateIcsCalendar — header", () => {
  it("generates valid VCALENDAR header with VERSION and PRODID", () => {
    const result = generateIcsCalendar(makeTrip());
    expect(result).toContain("BEGIN:VCALENDAR");
    expect(result).toContain("VERSION:2.0");
    expect(result).toContain("PRODID:-//Overplanned//Trip Calendar//EN");
    expect(result).toContain("CALSCALE:GREGORIAN");
    expect(result).toContain("METHOD:PUBLISH");
    expect(result).toContain("END:VCALENDAR");
  });

  it("includes X-WR-CALNAME with escaped trip name", () => {
    const result = generateIcsCalendar(makeTrip({ name: "Tokyo, Japan" }));
    expect(result).toContain("X-WR-CALNAME:Tokyo\\, Japan");
  });

  it("includes X-WR-TIMEZONE from first leg", () => {
    const result = generateIcsCalendar(makeTrip({
      legs: [{ city: "Tokyo", timezone: "Asia/Tokyo", startDate: "2026-07-01", endDate: "2026-07-04", dayOffset: 0 }],
    }));
    expect(result).toContain("X-WR-TIMEZONE:Asia/Tokyo");
  });
});

describe("generateIcsCalendar — single slot VEVENT", () => {
  it("generates VEVENT with correct DTSTART/DTEND for day 1 slot", () => {
    const trip = makeTrip({
      startDate: "2026-07-01",
      slots: [makeSlot({ startTime: "09:00", durationMinutes: 60 })],
    });
    const result = generateIcsCalendar(trip);

    expect(result).toContain("BEGIN:VEVENT");
    expect(result).toContain("DTSTART;TZID=Asia/Tokyo:20260701T090000");
    expect(result).toContain("DTEND;TZID=Asia/Tokyo:20260701T100000");
    expect(result).toContain("SUMMARY:Tsukiji Market");
    expect(result).toContain("DESCRIPTION:dining");
    expect(result).toContain("UID:slot-1@overplanned.app");
    expect(result).toContain("END:VEVENT");
  });

  it("generates DTSTAMP in UTC format", () => {
    const trip = makeTrip({ slots: [makeSlot()] });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("DTSTAMP:20260615T120000Z");
  });
});

describe("generateIcsCalendar — multi-day trip", () => {
  it("generates events on correct dates for different dayNumbers", () => {
    const trip = makeTrip({
      startDate: "2026-07-01",
      legs: [
        {
          city: "Tokyo",
          timezone: "Asia/Tokyo",
          startDate: "2026-07-01",
          endDate: "2026-07-04",
          dayOffset: 0,
        },
      ],
      slots: [
        makeSlot({ id: "s1", dayNumber: 1, startTime: "10:00", durationMinutes: 60 }),
        makeSlot({
          id: "s2",
          dayNumber: 3,
          startTime: "14:00",
          durationMinutes: 90,
          activityNode: { name: "Meiji Shrine", category: "culture" },
        }),
      ],
    });
    const result = generateIcsCalendar(trip);

    // Day 1 = July 1
    expect(result).toContain("DTSTART;TZID=Asia/Tokyo:20260701T100000");
    // Day 3 = July 3
    expect(result).toContain("DTSTART;TZID=Asia/Tokyo:20260703T140000");
    expect(result).toContain("DTEND;TZID=Asia/Tokyo:20260703T153000");
  });
});

describe("generateIcsCalendar — empty slots", () => {
  it("produces valid but empty calendar when slots array is empty", () => {
    const result = generateIcsCalendar(makeTrip({ slots: [] }));
    expect(result).toContain("BEGIN:VCALENDAR");
    expect(result).toContain("END:VCALENDAR");
    expect(result).not.toContain("BEGIN:VEVENT");
  });
});

describe("generateIcsCalendar — null activityNode", () => {
  it("skips slots with null activityNode", () => {
    const trip = makeTrip({
      slots: [
        makeSlot({ id: "s1", activityNode: null }),
        makeSlot({ id: "s2", activityNode: { name: "Valid", category: "food" } }),
      ],
    });
    const result = generateIcsCalendar(trip);

    // Only one VEVENT
    const veventCount = (result.match(/BEGIN:VEVENT/g) || []).length;
    expect(veventCount).toBe(1);
    expect(result).toContain("UID:s2@overplanned.app");
    expect(result).not.toContain("UID:s1@overplanned.app");
  });
});

describe("generateIcsCalendar — RFC 5545 escaping", () => {
  it("escapes commas in activity names", () => {
    const trip = makeTrip({
      slots: [makeSlot({ activityNode: { name: "Ramen, Sushi, Tempura", category: "dining" } })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("SUMMARY:Ramen\\, Sushi\\, Tempura");
  });

  it("escapes semicolons in activity names", () => {
    const trip = makeTrip({
      slots: [makeSlot({ activityNode: { name: "Food; Drinks", category: "dining" } })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("SUMMARY:Food\\; Drinks");
  });

  it("escapes backslashes in activity names", () => {
    const trip = makeTrip({
      slots: [makeSlot({ activityNode: { name: "Path\\to\\place", category: "culture" } })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("SUMMARY:Path\\\\to\\\\place");
  });

  it("escapes newlines in activity names", () => {
    const trip = makeTrip({
      slots: [makeSlot({ activityNode: { name: "Line1\nLine2", category: "culture" } })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("SUMMARY:Line1\\nLine2");
  });
});

describe("generateIcsCalendar — CRLF line endings", () => {
  it("uses CRLF line endings throughout the output", () => {
    const trip = makeTrip({ slots: [makeSlot()] });
    const result = generateIcsCalendar(trip);

    // Every line should end with \r\n, not bare \n
    const lines = result.split("\r\n");
    // Last element will be empty string from trailing \r\n
    expect(lines[lines.length - 1]).toBe("");
    // There should be no bare \n that aren't part of \r\n
    const stripped = result.replace(/\r\n/g, "");
    expect(stripped).not.toContain("\n");
  });
});

describe("generateIcsCalendar — timezone fallback", () => {
  it("defaults timezone to UTC when legs have empty timezone", () => {
    const trip = makeTrip({
      legs: [{ city: "Unknown", timezone: "", startDate: "2026-07-01", endDate: "2026-07-04", dayOffset: 0 }],
      slots: [makeSlot({ startTime: "09:00" })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("X-WR-TIMEZONE:UTC");
    expect(result).toContain("DTSTART;TZID=UTC:");
  });
});

describe("generateIcsCalendar — sortOrder-based time defaults", () => {
  it("defaults sortOrder 1 to 09:00", () => {
    const trip = makeTrip({
      slots: [makeSlot({ sortOrder: 1, startTime: null })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("T090000");
  });

  it("defaults sortOrder 2 to 12:00", () => {
    const trip = makeTrip({
      slots: [makeSlot({ sortOrder: 2, startTime: null })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("T120000");
  });

  it("defaults sortOrder 3 to 15:00", () => {
    const trip = makeTrip({
      slots: [makeSlot({ sortOrder: 3, startTime: null })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("T150000");
  });

  it("defaults sortOrder 4+ to 18:00", () => {
    const trip = makeTrip({
      slots: [makeSlot({ sortOrder: 5, startTime: null })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("T180000");
  });

  it("uses default 90min duration when durationMinutes is null", () => {
    const trip = makeTrip({
      startDate: "2026-07-01",
      slots: [makeSlot({ sortOrder: 1, startTime: null, durationMinutes: null })],
    });
    const result = generateIcsCalendar(trip);
    // 09:00 + 90min = 10:30
    expect(result).toContain("DTSTART;TZID=Asia/Tokyo:20260701T090000");
    expect(result).toContain("DTEND;TZID=Asia/Tokyo:20260701T103000");
  });
});

describe("generateIcsCalendar — ISO datetime startTime handling", () => {
  it("extracts HH:MM from full ISO datetime startTime", () => {
    const trip = makeTrip({
      startDate: "2026-07-01",
      slots: [makeSlot({ startTime: "2026-07-01T14:30:00Z", durationMinutes: 60 })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("T143000");
  });

  it("handles HH:MM format startTime directly", () => {
    const trip = makeTrip({
      startDate: "2026-07-01",
      slots: [makeSlot({ startTime: "16:45", durationMinutes: 60 })],
    });
    const result = generateIcsCalendar(trip);
    expect(result).toContain("T164500");
  });
});
