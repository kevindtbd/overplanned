/**
 * POST /api/trips/[id]/pivot
 *
 * Creates a pivot event for a slot, fetching alternative ActivityNodes
 * scored by authority + vibe overlap + jitter.
 *
 * Auth-gated — user must be a joined member of the trip.
 * Caps: max 3 active pivots per trip, max 1 per slot.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { v4 as uuidv4 } from "uuid";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import {
  pivotCreateSchema,
  MAX_ACTIVE_PIVOTS_PER_TRIP,
  MAX_ACTIVE_PIVOTS_PER_SLOT,
} from "@/lib/validations/pivot";

/**
 * Score an alternative node against the trip's persona seed.
 * authorityScore * 0.4 + vibe overlap * 0.4 + random jitter * 0.2
 */
function scoreAlternative(
  node: { authorityScore: number | null; vibeTags: { vibeTag: { slug: string } }[] },
  personaSlugs: string[],
): number {
  const authority = (node.authorityScore ?? 0) * 0.4;

  let vibeOverlap = 0;
  if (personaSlugs.length > 0 && node.vibeTags.length > 0) {
    const nodeSlugs = new Set(node.vibeTags.map((vt) => vt.vibeTag.slug));
    const matches = personaSlugs.filter((s) => nodeSlugs.has(s)).length;
    vibeOverlap = (matches / personaSlugs.length) * 0.4;
  }

  const jitter = Math.random() * 0.2;
  return authority + vibeOverlap + jitter;
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const tripId = params.id;

  // Parse + validate body
  let rawBody: unknown;
  try {
    rawBody = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = pivotCreateSchema.safeParse(rawBody);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten() },
      { status: 400 },
    );
  }

  const { slotId, trigger, reason } = parsed.data;

  // Verify trip membership
  const membership = await prisma.tripMember.findUnique({
    where: { tripId_userId: { tripId, userId } },
    select: { status: true },
  });

  if (!membership || membership.status !== "joined") {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Fetch the slot with its activity node and trip context
  const slot = await prisma.itinerarySlot.findUnique({
    where: { id: slotId },
    include: {
      activityNode: {
        select: { id: true, city: true, category: true },
      },
      trip: {
        select: {
          id: true,
          status: true,
          personaSeed: true,
          slots: {
            select: { activityNodeId: true },
          },
        },
      },
    },
  });

  if (!slot || slot.tripId !== tripId) {
    return NextResponse.json({ error: "Slot not found" }, { status: 404 });
  }

  // Trip must be active
  if (slot.trip.status !== "active") {
    return NextResponse.json(
      { error: "Trip must be active for pivots" },
      { status: 409 },
    );
  }

  // Slot must be confirmed or active
  if (!["confirmed", "active"].includes(slot.status)) {
    return NextResponse.json(
      { error: "Slot must be confirmed or active for pivots" },
      { status: 409 },
    );
  }

  if (!slot.activityNode) {
    return NextResponse.json(
      { error: "Slot has no activity node" },
      { status: 409 },
    );
  }

  // --- Pivot caps (V11) ---
  const activePivotsForTrip = await prisma.pivotEvent.count({
    where: { tripId, status: "proposed" },
  });
  if (activePivotsForTrip >= MAX_ACTIVE_PIVOTS_PER_TRIP) {
    return NextResponse.json(
      { error: "Too many active pivots" },
      { status: 409 },
    );
  }

  const activePivotsForSlot = await prisma.pivotEvent.count({
    where: { slotId, status: "proposed" },
  });
  if (activePivotsForSlot >= MAX_ACTIVE_PIVOTS_PER_SLOT) {
    return NextResponse.json(
      { error: "Pivot already active for this slot" },
      { status: 409 },
    );
  }

  // --- Fetch alternatives ---
  const existingSlotNodeIds = slot.trip.slots
    .map((s: (typeof slot.trip.slots)[number]) => s.activityNodeId)
    .filter(Boolean) as string[];

  const alternatives = await prisma.activityNode.findMany({
    where: {
      city: slot.activityNode.city,
      category: slot.activityNode.category,
      status: "approved",
      id: { notIn: existingSlotNodeIds },
    },
    include: {
      vibeTags: {
        where: { vibeTag: { isActive: true } },
        include: { vibeTag: { select: { slug: true } } },
      },
    },
    take: 10,
  });

  // Extract persona vibe slugs for scoring
  const personaSeed = slot.trip.personaSeed as { vibes?: string[] } | null;
  const personaSlugs = personaSeed?.vibes ?? [];

  // Score and rank
  const scored = alternatives.map((node: (typeof alternatives)[number]) => ({
    node,
    score: scoreAlternative(node, personaSlugs),
  }));
  scored.sort((a, b) => b.score - a.score);
  const top3 = scored.slice(0, 3);

  const alternativeIds = top3.map((s) => s.node.id);

  // Create PivotEvent + BehavioralSignal atomically
  try {
    const pivotId = uuidv4();
    const [pivotEvent] = await prisma.$transaction([
      prisma.pivotEvent.create({
        data: {
          id: pivotId,
          tripId,
          slotId,
          triggerType: trigger,
          triggerPayload: reason ? { reason } : undefined,
          originalNodeId: slot.activityNode.id,
          alternativeIds,
          status: "proposed",
        },
      }),
      prisma.behavioralSignal.create({
        data: {
          id: uuidv4(),
          userId,
          tripId,
          slotId,
          activityNodeId: slot.activityNode.id,
          signalType: "pivot_initiated",
          signalValue: 1.0,
          tripPhase: "active",
          rawAction: `pivot_${trigger}`,
        },
      }),
    ]);

    // Build alternative response objects
    const alternativeDetails = top3.map((s: (typeof top3)[number]) => ({
      id: s.node.id,
      name: s.node.name,
      category: s.node.category,
      neighborhood: s.node.neighborhood,
      primaryImageUrl: s.node.primaryImageUrl,
      authorityScore: s.node.authorityScore,
      score: s.score,
    }));

    return NextResponse.json({
      pivotEvent,
      alternatives: alternativeDetails,
    });
  } catch (err) {
    console.error("Pivot creation failed:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
