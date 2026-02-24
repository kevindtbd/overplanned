/**
 * POST /api/signals/behavioral
 *
 * Writes a BehavioralSignal row from discover surface interactions.
 * Auth-gated — userId always comes from session, never the request body.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { v4 as uuidv4 } from "uuid";
import { prisma } from "@/lib/prisma";
import { z } from "zod";

const VALID_SIGNAL_TYPES = [
  "discover_swipe_right",
  "discover_swipe_left",
  "discover_shortlist",
  "discover_remove",
  "slot_view",
  "slot_tap",
  "slot_confirm",
  "slot_skip",
  "slot_swap",
  "slot_complete",
  "slot_dwell",
  "vibe_select",
  "vibe_deselect",
  "vibe_implicit",
  "post_loved",
  "post_skipped",
  "post_missed",
  "post_disliked",
  "pivot_accepted",
  "pivot_rejected",
  "pivot_initiated",
  "dwell_time",
  "scroll_depth",
  "return_visit",
  "share_action",
  "vote_cast",
  "invite_accepted",
  "invite_declined",
  "trip_shared",
  "trip_imported",
  "packing_checked",
  "packing_unchecked",
  "mood_reported",
  "slot_moved",
] as const;

const VALID_PHASES = ["pre_trip", "active", "post_trip"] as const;

const behavioralSignalSchema = z.object({
  tripId: z.string().uuid().optional().nullable(),
  slotId: z.string().uuid().optional().nullable(),
  activityNodeId: z.string().uuid().optional().nullable(),
  signalType: z.enum(VALID_SIGNAL_TYPES, {
    errorMap: () => ({ message: "Unknown signalType" }),
  }),
  signalValue: z.number().optional().default(0),
  tripPhase: z.enum(VALID_PHASES, {
    errorMap: () => ({ message: "Unknown tripPhase" }),
  }),
  rawAction: z.string().min(1),
  weatherContext: z.string().optional().nullable(),
  modelVersion: z.string().optional().nullable(),
  promptVersion: z.string().optional().nullable(),
});

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
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
  } = parsed.data;

  try {
    await prisma.behavioralSignal.create({
      data: {
        id: uuidv4(),
        userId,
        tripId: tripId ?? null,
        slotId: slotId ?? null,
        activityNodeId: activityNodeId ?? null,
        signalType,
        signalValue,
        tripPhase,
        rawAction,
        weatherContext: weatherContext ?? null,
        modelVersion: modelVersion ?? null,
        promptVersion: promptVersion ?? null,
      },
    });

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[signals/behavioral] DB error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
