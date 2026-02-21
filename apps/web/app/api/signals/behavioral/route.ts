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

const VALID_SIGNAL_TYPES = new Set([
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
]);

const VALID_PHASES = new Set(["pre_trip", "active", "post_trip"]);

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
  } = body;

  if (!signalType || !tripPhase || !rawAction) {
    return NextResponse.json(
      { error: "signalType, tripPhase, and rawAction are required" },
      { status: 400 }
    );
  }

  if (!VALID_SIGNAL_TYPES.has(String(signalType))) {
    return NextResponse.json(
      { error: `Unknown signalType: ${signalType}` },
      { status: 400 }
    );
  }

  if (!VALID_PHASES.has(String(tripPhase))) {
    return NextResponse.json(
      { error: `Unknown tripPhase: ${tripPhase}` },
      { status: 400 }
    );
  }

  try {
    await prisma.behavioralSignal.create({
      data: {
        id: uuidv4(),
        userId,
        tripId: tripId ? String(tripId) : null,
        slotId: slotId ? String(slotId) : null,
        activityNodeId: activityNodeId ? String(activityNodeId) : null,
        signalType: String(signalType) as never,
        signalValue: typeof signalValue === "number" ? signalValue : 0,
        tripPhase: String(tripPhase) as never,
        rawAction: String(rawAction),
        weatherContext: weatherContext ? String(weatherContext) : null,
        modelVersion: modelVersion ? String(modelVersion) : null,
        promptVersion: promptVersion ? String(promptVersion) : null,
      },
    });

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[signals/behavioral] DB error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
