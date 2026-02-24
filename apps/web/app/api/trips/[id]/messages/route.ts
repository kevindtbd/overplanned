/**
 * GET  /api/trips/[id]/messages — List messages with cursor pagination
 * POST /api/trips/[id]/messages — Send a message (optionally with slot reference)
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { rateLimit, rateLimitPresets } from "@/lib/rate-limit";
import { messageCreateSchema, messageCursorSchema } from "@/lib/validations/messages";
import { requireAuth, requireTripMember } from "@/lib/api/helpers";
import { sanitize } from "@/lib/api/sanitize";

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const auth = await requireAuth();
  if (auth instanceof NextResponse) return auth;
  const { userId } = auth;

  const { id: tripId } = params;

  try {
    const membership = await requireTripMember(tripId, userId);
    if (membership instanceof NextResponse) return membership;

    // Parse query params
    const searchParams = Object.fromEntries(req.nextUrl.searchParams.entries());
    const parsed = messageCursorSchema.safeParse(searchParams);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
        { status: 400 }
      );
    }

    const { cursor, limit } = parsed.data;

    // Resolve cursor to createdAt for keyset pagination
    let cursorMessage: { createdAt: Date; id: string } | null = null;
    if (cursor) {
      cursorMessage = await prisma.message.findUnique({
        where: { id: cursor },
        select: { createdAt: true, id: true },
      });
    }

    const messages = await prisma.message.findMany({
      where: {
        tripId,
        ...(cursorMessage
          ? {
              OR: [
                { createdAt: { lt: cursorMessage.createdAt } },
                { createdAt: cursorMessage.createdAt, id: { lt: cursorMessage.id } },
              ],
            }
          : {}),
      },
      orderBy: [{ createdAt: "desc" }, { id: "desc" }],
      take: limit,
      include: {
        user: { select: { id: true, name: true, avatarUrl: true } },
        slotRef: {
          select: {
            id: true,
            dayNumber: true,
            startTime: true,
            wasSwapped: true,
            status: true,
            activityNode: { select: { name: true, category: true } },
          },
        },
      },
    });

    // Add isStale flag to messages with slot references
    const enriched = messages.map((msg) => ({
      ...msg,
      slotRef: msg.slotRef
        ? {
            ...msg.slotRef,
            isStale: msg.slotRef.wasSwapped || msg.slotRef.status === "skipped",
          }
        : null,
    }));

    const nextCursor =
      enriched.length === limit ? enriched[enriched.length - 1].id : null;

    return NextResponse.json({ messages: enriched, nextCursor });
  } catch (err) {
    console.error(`[GET /api/trips/${tripId}/messages] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const auth = await requireAuth();
  if (auth instanceof NextResponse) return auth;
  const { userId } = auth;

  const { id: tripId } = params;

  // Rate limit
  const rateLimited = rateLimit(req, rateLimitPresets.authenticated, `chat:${userId}`);
  if (rateLimited) return rateLimited;

  try {
    const membership = await requireTripMember(tripId, userId);
    if (membership instanceof NextResponse) return membership;

    // Parse body
    let body: unknown;
    try {
      body = await req.json();
    } catch {
      return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
    }

    const parsed = messageCreateSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: "Validation failed", details: parsed.error.flatten() },
        { status: 400 }
      );
    }

    const { slotRefId } = parsed.data;
    const sanitizedBody = sanitize(parsed.data.body);

    // Verify slotRef belongs to this trip
    if (slotRefId) {
      const slot = await prisma.itinerarySlot.findFirst({
        where: { id: slotRefId, tripId },
      });
      if (!slot) {
        return NextResponse.json(
          { error: "Slot not found in this trip" },
          { status: 400 }
        );
      }
    }

    // Create message (+ optional behavioral signal) in transaction
    const operations = [
      prisma.message.create({
        data: {
          tripId,
          userId,
          body: sanitizedBody,
          slotRefId: slotRefId || null,
        },
        include: {
          user: { select: { id: true, name: true, avatarUrl: true } },
          slotRef: {
            select: {
              id: true,
              dayNumber: true,
              startTime: true,
              wasSwapped: true,
              status: true,
              activityNode: { select: { name: true, category: true } },
            },
          },
        },
      }),
      ...(slotRefId
        ? [
            prisma.behavioralSignal.create({
              data: {
                userId,
                tripId,
                slotId: slotRefId,
                signalType: "share_action",
                signalValue: 1.0,
                rawAction: `slot_share:${slotRefId}`,
                tripPhase: "active",
              },
            }),
          ]
        : []),
    ];

    const results = await prisma.$transaction(operations);
    const message = results[0];

    return NextResponse.json(message, { status: 201 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/messages] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
