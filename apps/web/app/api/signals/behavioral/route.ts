/**
 * POST /api/signals/behavioral
 *
 * Writes a BehavioralSignal row from discover surface interactions.
 * Auth-gated -- userId always comes from session, never the request body.
 *
 * Enhancements (C.WT4):
 * - Server-side signal type allowlist
 * - signalValue clamping to [-1.0, 1.0]
 * - Per-user rate limiting (in-memory, single-instance)
 * - Weather context auto-attach from trip data
 * - candidateSetId / candidateIds persistence
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { v4 as uuidv4 } from "uuid";
import { prisma, type SignalType, type Prisma } from "@/lib/prisma";
import { z } from "zod";

// ---------------------------------------------------------------------------
// Signal type allowlist (server-side gate)
// ---------------------------------------------------------------------------

const ALLOWED_SIGNAL_TYPES = new Set([
  // Explicit (Tier 1)
  "slot_confirmed", "slot_rejected",
  "pre_trip_slot_swap", "pre_trip_slot_removed",
  // Strong implicit (Tier 2)
  "slot_locked", "pre_trip_slot_added", "pre_trip_reorder", "discover_shortlist",
  // Weak implicit (Tier 3)
  "card_viewed", "card_dismissed", "slot_moved",
  "discover_swipe_right", "discover_swipe_left",
  // Passive (Tier 4)
  "card_impression", "pivot_accepted", "pivot_rejected",
]);

// ---------------------------------------------------------------------------
// Rate limiting (in-memory, per-user sliding window)
// ---------------------------------------------------------------------------

const RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute
const MAX_SIGNALS_PER_WINDOW = 120;  // 2 per second average

interface RateLimitEntry {
  count: number;
  windowStart: number;
}

const rateLimitMap = new Map<string, RateLimitEntry>();

function isRateLimited(userId: string): boolean {
  const now = Date.now();
  const entry = rateLimitMap.get(userId);

  if (!entry || now - entry.windowStart >= RATE_LIMIT_WINDOW_MS) {
    rateLimitMap.set(userId, { count: 1, windowStart: now });
    return false;
  }

  entry.count += 1;
  return entry.count > MAX_SIGNALS_PER_WINDOW;
}


// ---------------------------------------------------------------------------
// Season helper
// ---------------------------------------------------------------------------

function getSeason(date: Date): string {
  const month = date.getMonth() + 1; // 1-indexed
  if (month >= 3 && month <= 5) return "spring";
  if (month >= 6 && month <= 8) return "summer";
  if (month >= 9 && month <= 11) return "autumn";
  return "winter";
}

// ---------------------------------------------------------------------------
// Validation schema
// ---------------------------------------------------------------------------

const VALID_PHASES = ["pre_trip", "active", "post_trip"] as const;

const behavioralSignalSchema = z.object({
  tripId: z.string().uuid().optional().nullable(),
  slotId: z.string().uuid().optional().nullable(),
  activityNodeId: z.string().uuid().optional().nullable(),
  signalType: z.string().min(1),
  signalValue: z.number().optional().default(0),
  tripPhase: z.enum(VALID_PHASES, {
    errorMap: () => ({ message: "Unknown tripPhase" }),
  }),
  rawAction: z.string().min(1),
  weatherContext: z.string().optional().nullable(),
  modelVersion: z.string().optional().nullable(),
  promptVersion: z.string().optional().nullable(),
  candidateSetId: z.string().uuid().optional().nullable(),
  candidateIds: z.array(z.string().uuid()).optional().nullable(),
  metadata: z.record(z.unknown()).optional().nullable(),
});

// ---------------------------------------------------------------------------
// POST handler
// ---------------------------------------------------------------------------

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  // Rate limit check
  if (isRateLimited(userId)) {
    return NextResponse.json(
      { error: "Too many signals. Try again later." },
      { status: 429 }
    );
  }

  let rawBody: unknown;
  try {
    rawBody = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = behavioralSignalSchema.safeParse(rawBody);
  if (!parsed.success) {
    const fieldErrors = parsed.error.flatten().fieldErrors;
    const firstError =
      fieldErrors.signalType?.[0] ??
      fieldErrors.tripPhase?.[0] ??
      fieldErrors.rawAction?.[0] ??
      "Validation failed";
    return NextResponse.json({ error: firstError }, { status: 400 });
  }

  const {
    tripId,
    slotId,
    activityNodeId,
    signalType,
    signalValue,
    tripPhase,
    rawAction,
    weatherContext,
    modelVersion,
    promptVersion,
    candidateSetId,
    candidateIds,
    metadata: clientMetadata,
  } = parsed.data;

  // Server-side allowlist check
  if (!ALLOWED_SIGNAL_TYPES.has(signalType)) {
    return NextResponse.json(
      { error: `Unknown signalType: ${signalType}` },
      { status: 400 }
    );
  }

  // Clamp signalValue to [-1.0, 1.0]
  const clampedValue = Math.max(-1, Math.min(1, signalValue));

  // Build metadata object (merge client metadata + server enrichments)
  const enrichedMetadata: Record<string, unknown> = {
    ...(clientMetadata ?? {}),
  };

  // Weather context auto-attach: look up trip's first leg for city/dates
  if (tripId) {
    try {
      const tripLeg = await prisma.tripLeg.findFirst({
        where: { tripId },
        orderBy: { position: "asc" },
        select: { city: true, startDate: true },
      });

      if (tripLeg?.city && tripLeg?.startDate) {
        enrichedMetadata.weatherContext = {
          city: tripLeg.city,
          month: tripLeg.startDate.getMonth() + 1,
          season: getSeason(tripLeg.startDate),
        };
      }
    } catch (err) {
      // Non-fatal: log but don't fail the signal write
      console.warn("[signals/behavioral] Weather lookup failed:", err);
    }
  }

  try {
    await prisma.behavioralSignal.create({
      data: {
        id: uuidv4(),
        userId,
        tripId: tripId ?? null,
        slotId: slotId ?? null,
        activityNodeId: activityNodeId ?? null,
        signalType: signalType as SignalType,
        signalValue: clampedValue,
        tripPhase,
        rawAction,
        weatherContext: weatherContext ?? null,
        modelVersion: modelVersion ?? null,
        promptVersion: promptVersion ?? null,
        candidateSetId: candidateSetId ?? null,
        candidateIds: candidateIds ?? undefined,
        metadata: Object.keys(enrichedMetadata).length > 0
          ? (enrichedMetadata as Prisma.InputJsonValue)
          : undefined,
      },
    });

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[signals/behavioral] DB error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
