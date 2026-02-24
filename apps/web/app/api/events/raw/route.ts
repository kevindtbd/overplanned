/**
 * POST /api/events/raw
 *
 * Thin proxy for single-event writes from the discover surface.
 * Forwards to the existing /events/batch endpoint on the FastAPI service,
 * wrapping the single event in the batch envelope.
 *
 * The batch endpoint on services/api is internal-only.
 * This route handles auth and adds userId from the session.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { v4 as uuidv4 } from "uuid";
import { prisma } from "@/lib/prisma";

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  let body: Record<string, unknown>;

  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const {
    sessionId,
    tripId,
    activityNodeId,
    clientEventId,
    eventType,
    intentClass,
    surface,
    payload,
    platform,
    screenWidth,
    networkType,
  } = body;

  if (!sessionId || !eventType || !intentClass) {
    return NextResponse.json(
      { error: "sessionId, eventType, and intentClass are required" },
      { status: 400 }
    );
  }

  try {
    await prisma.rawEvent.create({
      data: {
        id: uuidv4(),
        userId,
        sessionId: String(sessionId),
        tripId: tripId ? String(tripId) : null,
        activityNodeId: activityNodeId ? String(activityNodeId) : null,
        clientEventId: clientEventId ? String(clientEventId) : null,
        eventType: String(eventType),
        intentClass: String(intentClass) as "explicit" | "implicit" | "contextual",
        surface: surface ? String(surface) : null,
        payload: (payload ?? {}) as import("@prisma/client").Prisma.InputJsonValue,
        platform: platform ? String(platform) : null,
        screenWidth: screenWidth ? Number(screenWidth) : null,
        networkType: networkType ? String(networkType) : null,
      },
    });

    return NextResponse.json({ success: true });
  } catch (err: unknown) {
    // Unique constraint violation (duplicate clientEventId) — treat as success
    if (
      err instanceof Error &&
      err.message.includes("Unique constraint")
    ) {
      return NextResponse.json({ success: true, deduped: true });
    }

    console.error("[events/raw] DB error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
