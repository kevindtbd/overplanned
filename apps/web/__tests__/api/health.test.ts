/**
 * Route handler tests for GET /api/health
 * No auth required — this endpoint is public so Cloud Run healthchecks can reach it.
 */

import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    $queryRaw: vi.fn().mockResolvedValue([{ "?column?": 1 }]),
  },
}));

const { GET } = await import("../../app/api/health/route");

describe("GET /api/health", () => {
  it("returns 200 with { status: 'ok' } when DB is healthy", async () => {
    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.status).toBe("ok");
    expect(json.checks).toEqual({ database: "ok" });
  });

  it("returns 503 with degraded when DB is down", async () => {
    const { prisma } = await import("@/lib/prisma");
    const mocked = vi.mocked(prisma, true);
    mocked.$queryRaw.mockRejectedValueOnce(new Error("connection refused"));

    const res = await GET();
    expect(res.status).toBe(503);

    const json = await res.json();
    expect(json.status).toBe("degraded");
    expect(json.checks).toEqual({ database: "error" });
  });
});
