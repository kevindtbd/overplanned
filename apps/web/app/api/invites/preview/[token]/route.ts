/**
 * GET /api/invites/preview/[token] — Public invite preview (no auth required)
 * Returns trip summary for invite page display. Rate limited.
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { joinQuerySchema } from "@/lib/validations/invite";

export async function GET(
  _req: NextRequest,
  { params }: { params: { token: string } }
) {
  const parsed = joinQuerySchema.safeParse({ token: params.token });
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid token format" }, { status: 400 });
  }

  const { token } = parsed.data;

  try {
    const invite = await prisma.inviteToken.findUnique({
      where: { token },
      include: {
        trip: {
          select: {
            id: true,
            name: true,
            startDate: true,
            endDate: true,
            status: true,
            members: {
              where: { status: "joined" },
              select: { id: true },
            },
            legs: {
              orderBy: { position: "asc" },
              take: 1,
              select: {
                destination: true,
                city: true,
                country: true,
              },
            },
          },
        },
      },
    });

    if (!invite) {
      return NextResponse.json({ error: "Invite not found", valid: false }, { status: 404 });
    }

    // Check validity: not expired, not revoked, uses remaining
    const now = new Date();
    if (invite.revokedAt || invite.expiresAt < now || invite.usedCount >= invite.maxUses) {
      return NextResponse.json({ error: "Invite is no longer valid", valid: false }, { status: 410 });
    }

    const trip = invite.trip;
    const firstLeg = trip.legs[0];

    // Look up organizer name
    const organizer = await prisma.tripMember.findFirst({
      where: { tripId: trip.id, role: "organizer", status: "joined" },
      select: {
        user: { select: { name: true } },
      },
    });

    const organizerName = organizer?.user?.name?.split(" ")[0] ?? "Someone";

    return NextResponse.json({
      tripId: trip.id,
      destination: firstLeg?.destination ?? trip.name ?? "A trip",
      city: firstLeg?.city ?? null,
      country: firstLeg?.country ?? null,
      startDate: trip.startDate,
      endDate: trip.endDate,
      memberCount: trip.members.length,
      organizerName,
      valid: true,
    });
  } catch (err) {
    console.error(`[GET /api/invites/preview/${token}] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
