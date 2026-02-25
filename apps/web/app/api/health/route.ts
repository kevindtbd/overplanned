import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function GET() {
  const checks: Record<string, "ok" | "error"> = {};
  const latency: Record<string, number> = {};

  // DB connectivity + latency
  try {
    const start = performance.now();
    await prisma.$queryRaw`SELECT 1`;
    latency.database = Math.round(performance.now() - start);
    checks.database = "ok";
  } catch {
    checks.database = "error";
  }

  const healthy = Object.values(checks).every((v) => v === "ok");

  return NextResponse.json(
    { status: healthy ? "ok" : "degraded", checks, latency },
    { status: healthy ? 200 : 503 },
  );
}
