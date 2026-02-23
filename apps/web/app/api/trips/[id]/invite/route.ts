/**
 * POST /api/trips/[id]/invite — Create an invite token (organizer only, group mode)
 * Returns invite URL with secure 256-bit token (V2).
 */

import crypto from "crypto";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { inviteCreateSchema } from "@/lib/validations/invite";

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

  // Parse optional body (defaults applied by Zod)
  let body: unknown = {};
  try {
    const text = await req.text();
    if (text) body = JSON.parse(text);
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = inviteCreateSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  try {
    // Auth: must be organizer + joined member
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { role: true, status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    if (membership.role !== "organizer") {
      return NextResponse.json(
        { error: "Only the trip organizer can create invites" },
        { status: 403 }
      );
    }

    // Verify trip is group mode
    const trip = await prisma.trip.findUnique({
      where: { id: tripId },
      select: { mode: true, status: true },
    });

    if (!trip) {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    if (trip.mode !== "group") {
      return NextResponse.json(
        { error: "Invites are only available for group trips" },
        { status: 409 }
      );
    }

    // Generate secure 256-bit token (V2)
    const token = crypto.randomBytes(32).toString("base64url");

    const { maxUses, expiresInDays } = parsed.data;
    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + expiresInDays);

    const invite = await prisma.inviteToken.create({
      data: {
        tripId,
        token,
        createdBy: userId,
        maxUses,
        expiresAt,
      },
    });

    // Build invite URL using env var (production) or request origin (local dev)
    const baseUrl = process.env.NEXT_PUBLIC_APP_URL || req.nextUrl.origin;
    const inviteUrl = `${baseUrl}/invite/${invite.token}`;

    return NextResponse.json(
      { token: invite.token, inviteUrl, expiresAt: invite.expiresAt },
      { status: 201 }
    );
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/invite] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
