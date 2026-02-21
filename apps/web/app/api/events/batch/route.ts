/**
 * POST /api/events/batch
 *
 * Receives batched RawEvents from the client-side EventEmitter and persists
 * them to the RawEvent table.
 *
 * Auth: userId always sourced from session — never trusted from the request body.
 * Dedup: createMany with skipDuplicates leverages @@unique([userId, clientEventId]).
 * Cap: 50 events per request (enforced by Zod, not just a code check).
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { Prisma } from "@prisma/client";
import { z } from "zod";
import type { EventBatchResponse } from "@/lib/events/types";

// ---------------------------------------------------------------------------
// Validation schemas
// ---------------------------------------------------------------------------

const eventSchema = z.object({
  clientEventId: z.string().uuid(),
  sessionId: z.string().uuid(),
  timestamp: z.string().datetime(),
  intentClass: z.enum(["explicit", "implicit", "contextual"]),
  eventType: z.string().min(1).max(50),
  tripId: z.string().uuid().optional(),
  slotId: z.string().optional(),
  activityNodeId: z.string().uuid().optional(),
  /** Strip any userId the client may have smuggled in here — we never use it. */
  payload: z.record(z.unknown()).default({}),
});

const batchSchema = z.object({
  sessionId: z.string().uuid(),
  events: z.array(eventSchema).min(1).max(50),
});

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function POST(req: NextRequest) {
  // 1. Auth gate — userId always comes from the verified session
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  // 2. Parse JSON body
  let rawBody: unknown;
  try {
    rawBody = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // 3. Zod validation — batch size cap is enforced here (max 50)
  const parsed = batchSchema.safeParse(rawBody);
  if (!parsed.success) {
    return NextResponse.json(
      {
        error: "Validation failed",
        details: parsed.error.flatten(),
      },
      { status: 422 }
    );
  }

  const { events } = parsed.data;

  // 4. Build insert rows — strip any userId from payload, always use session userId
  const rows: Prisma.RawEventCreateManyInput[] = events.map((event) => {
    // Destructure payload to ensure userId cannot leak through
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { userId: _dropped, ...safePayload } = event.payload as Record<string, unknown>;

    // Prefer the sanitized payload (no userId); fall back to raw payload only if
    // nothing was stripped (i.e. _dropped was undefined).
    const finalPayload: Prisma.InputJsonValue =
      _dropped !== undefined
        ? (safePayload as Prisma.InputJsonValue)
        : (event.payload as Prisma.InputJsonValue);

    return {
      // id is @default(uuid()) in schema — Prisma generates it
      userId,
      sessionId: event.sessionId,
      tripId: event.tripId ?? null,
      activityNodeId: event.activityNodeId ?? null,
      clientEventId: event.clientEventId,
      eventType: event.eventType,
      intentClass: event.intentClass,
      // slotId is not a RawEvent column — carried in payload if needed
      payload: finalPayload,
      surface: null,
      platform: null,
      screenWidth: null,
      networkType: null,
    };
  });

  // 5. Batch insert with dedup via @@unique([userId, clientEventId])
  let createResult: { count: number };
  try {
    createResult = await prisma.rawEvent.createMany({
      data: rows,
      skipDuplicates: true,
    });
  } catch (err: unknown) {
    console.error("[events/batch] DB error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }

  // 6. Return accepted/duplicates breakdown
  const accepted = createResult.count;
  const duplicates = events.length - accepted;

  const response: EventBatchResponse = { accepted, duplicates };
  return NextResponse.json(response, { status: 200 });
}
