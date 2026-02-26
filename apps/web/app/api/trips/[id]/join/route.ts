/**
 * POST /api/trips/[id]/join?token=xxx — Join a trip via invite token
 * Auth required. Token passed as query param (matches InviteJoinButton.tsx).
 * Uses atomic SQL to prevent TOCTOU race on usedCount (V1).
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { joinQuerySchema } from "@/lib/validations/invite";

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  // Validate token from query param
  const tokenParam = req.nextUrl.searchParams.get("token");
  const parsed = joinQuerySchema.safeParse({ token: tokenParam });
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid or missing token" },
      { status: 400 }
    );
  }

  const { token } = parsed.data;

  try {
    // Check if user is already a joined member of this trip
    const existingMembership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
    });

    if (existingMembership && existingMembership.status === "joined") {
      return NextResponse.json({ error: "Already a member" }, { status: 409 });
    }

    // Atomic increment — prevents TOCTOU race (V1)
    // Only succeeds if: token matches trip, not revoked, not expired, uses remaining
    const updated = await prisma.$queryRaw<Array<{ id: string; role: string }>>`
      UPDATE invite_tokens SET "usedCount" = "usedCount" + 1
      WHERE token = ${token} AND "usedCount" < "maxUses"
      AND "revokedAt" IS NULL AND "expiresAt" > NOW()
      AND "tripId" = ${tripId}
      RETURNING id, role
    `;

    if (!updated || updated.length === 0) {
      return NextResponse.json(
        { error: "Invite is invalid, expired, or fully used" },
        { status: 409 }
      );
    }

    const inviteRole = updated[0].role as "organizer" | "member";

    // Create or update membership + log signal in a transaction
    await prisma.$transaction([
      existingMembership
        ? prisma.tripMember.update({
            where: { tripId_userId: { tripId, userId } },
            data: { status: "joined", role: inviteRole, joinedAt: new Date() },
          })
        : prisma.tripMember.create({
            data: {
              tripId,
              userId,
              role: inviteRole,
              status: "joined",
              joinedAt: new Date(),
            },
          }),
      prisma.behavioralSignal.create({
        data: {
          userId,
          tripId,
          signalType: "invite_accepted",
          signalValue: 1.0,
          tripPhase: "pre_trip",
          rawAction: `join_via_invite:${token.slice(0, 8)}`,
        },
      }),
    ]);

    return NextResponse.json({ tripId }, { status: 200 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/join] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
