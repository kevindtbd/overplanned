/**
 * POST /api/slots/[slotId]/vote
 *
 * Casts a vote on an ItinerarySlot and checks quorum for auto-confirm/contest.
 *
 * Auth-gated -- user must be a joined member of the trip that owns this slot.
 * Uses serializable-style read-modify-write on voteState JSON.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { v4 as uuidv4 } from "uuid";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import {
  voteSchema,
  VOTE_SIGNAL_VALUES,
  VOTE_CONFIRM_THRESHOLD,
} from "@/lib/validations/vote";

interface VoteState {
  state: "voting" | "confirmed" | "contested";
  votes: Record<string, string>;
  updatedAt: string;
}

export async function POST(
  req: NextRequest,
  { params }: { params: { slotId: string } },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { slotId } = params;

  // Parse + validate body
  let rawBody: unknown;
  try {
    rawBody = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = voteSchema.safeParse(rawBody);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten() },
      { status: 400 },
    );
  }

  const { vote } = parsed.data;

  // Fetch slot and verify joined trip membership in one query
  const slot = await prisma.itinerarySlot.findUnique({
    where: { id: slotId },
    include: {
      trip: {
        include: {
          members: { where: { userId, status: "joined" } },
        },
      },
    },
  });

  if (!slot || slot.trip.members.length === 0) {
    return NextResponse.json(
      { error: "Slot not found" },
      { status: 404 },
    );
  }

  // Read current voteState or initialize
  const currentVoteState = (slot.voteState as VoteState | null) ?? {
    state: "voting" as const,
    votes: {},
    updatedAt: new Date().toISOString(),
  };

  // If state was null/proposed, first vote transitions to "voting"
  const voteState: VoteState = {
    state: currentVoteState.state === "confirmed" || currentVoteState.state === "contested"
      ? currentVoteState.state
      : "voting",
    votes: { ...currentVoteState.votes },
    updatedAt: new Date().toISOString(),
  };

  // Set vote
  voteState.votes[userId] = vote;

  // Count quorum: all joined members at vote time
  const totalMembers = await prisma.tripMember.count({
    where: { tripId: slot.tripId, status: "joined" },
  });

  const votesCast = Object.keys(voteState.votes).length;

  // Prepare slot update data
  const updateData: Record<string, unknown> = {
    voteState: voteState as unknown,
    updatedAt: new Date(),
  };

  // Check if all members have voted
  if (votesCast >= totalMembers) {
    const yesCount = Object.values(voteState.votes).filter(
      (v) => v === "yes",
    ).length;

    if (yesCount / totalMembers >= VOTE_CONFIRM_THRESHOLD) {
      voteState.state = "confirmed";
      updateData.voteState = voteState as unknown;
      updateData.status = "confirmed";
    } else {
      voteState.state = "contested";
      updateData.voteState = voteState as unknown;
      updateData.isContested = true;
    }
  }

  // Atomic update: slot + behavioral signal
  try {
    const [updatedSlot] = await prisma.$transaction([
      prisma.itinerarySlot.update({
        where: { id: slotId },
        data: updateData,
      }),
      prisma.behavioralSignal.create({
        data: {
          id: uuidv4(),
          userId,
          tripId: slot.tripId,
          slotId,
          activityNodeId: slot.activityNodeId,
          signalType: "vote_cast" as never,
          signalValue: VOTE_SIGNAL_VALUES[vote],
          tripPhase: "pre_trip",
          rawAction: `vote_${vote}`,
        },
      }),
    ]);

    return NextResponse.json({
      success: true,
      data: {
        voteState: (updatedSlot.voteState as VoteState),
        slotStatus: updatedSlot.status,
      },
    });
  } catch (err) {
    console.error("Vote update failed:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
