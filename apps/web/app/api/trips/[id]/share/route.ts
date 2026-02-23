/**
 * POST /api/trips/[id]/share — Create a shared trip token (organizer only)
 */

import crypto from "crypto";
import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { shareCreateSchema } from "@/lib/validations/share";

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

  // Parse optional body (expiresInDays defaults to 30)
  let body: unknown = {};
  try {
    const text = await req.text();
    if (text) body = JSON.parse(text);
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = shareCreateSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  try {
    // IDOR: verify organizer + joined
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { role: true, status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    if (membership.role !== "organizer") {
      return NextResponse.json(
        { error: "Only the trip organizer can share this trip" },
        { status: 403 }
      );
    }

    const expiresInDays = parsed.data?.expiresInDays ?? 30;
    const token = crypto.randomBytes(32).toString("base64url");
    const expiresAt = new Date(Date.now() + expiresInDays * 24 * 60 * 60 * 1000);

    const sharedToken = await prisma.sharedTripToken.create({
      data: {
        tripId,
        token,
        createdBy: userId,
        expiresAt,
      },
    });

    // Log signal server-side
    await prisma.behavioralSignal.create({
      data: {
        userId,
        tripId,
        signalType: "share_action",
        signalValue: 1.0,
        tripPhase: "pre_trip",
        rawAction: "trip_shared",
      },
    });

    const shareUrl = `${process.env.NEXT_PUBLIC_APP_URL || ""}/s/${token}`;

    return NextResponse.json(
      { token, shareUrl, expiresAt: sharedToken.expiresAt.toISOString() },
      { status: 201 }
    );
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/share] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
