/**
 * GET /api/trips/[id]/expenses/settle — Compute settle-up for a trip
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { computeSettlements } from "@/lib/settle";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  try {
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    const [expenses, members, trip] = await Promise.all([
      prisma.expense.findMany({
        where: { tripId },
        select: { paidById: true, amountCents: true, splitWith: true },
      }),
      prisma.tripMember.findMany({
        where: { tripId, status: "joined" },
        select: {
          userId: true,
          user: { select: { id: true, name: true, avatarUrl: true } },
        },
      }),
      prisma.trip.findUnique({
        where: { id: tripId },
        select: { currency: true },
      }),
    ]);

    const memberIds = members.map((m) => m.userId);
    const settlements = computeSettlements(expenses, memberIds);

    // Build lookup for hydration
    const memberLookup = new Map(
      members.map((m) => [m.userId, m.user.name ?? "Unknown"])
    );

    const hydratedSettlements = settlements.map((s) => ({
      fromId: s.fromId,
      fromName: memberLookup.get(s.fromId) ?? "Unknown",
      toId: s.toId,
      toName: memberLookup.get(s.toId) ?? "Unknown",
      amountCents: s.amountCents,
    }));

    return NextResponse.json(
      { settlements: hydratedSettlements, currency: trip?.currency ?? "USD" },
      { status: 200 }
    );
  } catch (err) {
    console.error(`[GET /api/trips/${tripId}/expenses/settle] Error:`, err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
