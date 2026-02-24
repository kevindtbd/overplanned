/**
 * Route handler tests for GET /api/health
 * No auth required — this endpoint is public so Cloud Run healthchecks can reach it.
 */

import { describe, it, expect } from "vitest";
import { NextRequest } from "next/server";

const { GET } = await import("../../app/api/health/route");

function makeRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/health", {
    method: "GET",
  });
}

describe("GET /api/health", () => {
  it("returns 200 with { status: 'ok' }", async () => {
    const res = await GET();
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json).toEqual({ status: "ok" });
  });

  it("does not include a timestamp in the response", async () => {
    const res = await GET();
    const json = await res.json();
    expect(json).not.toHaveProperty("timestamp");
  });
});
