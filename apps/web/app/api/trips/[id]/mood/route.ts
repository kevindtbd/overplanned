import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { moodSchema } from "@/lib/validations/mood";
import { requireAuth } from "@/lib/api/helpers";

const MOOD_VALUE_MAP: Record<string, number> = {
  high: 1.0,
  medium: 0.5,
  low: 0.0,
};

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const auth = await requireAuth();
  if (auth instanceof NextResponse) return auth;
  const { userId } = auth;

  const tripId = params.id;

  // Membership check (needs energyProfile so we query directly)
  const member = await prisma.tripMember.findUnique({
    where: { tripId_userId: { tripId, userId } },
    select: { role: true, status: true, energyProfile: true },
  });

  if (!member || member.status !== "joined") {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Trip status check
  const trip = await prisma.trip.findUnique({
    where: { id: tripId },
    select: { status: true },
  });

  if (!trip || trip.status !== "active") {
    return NextResponse.json(
      { error: "Mood capture only available for active trips" },
      { status: 400 }
    );
  }

  // Validate body
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = moodSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid mood", details: parsed.error.flatten() },
      { status: 400 }
    );
  }

  const { mood } = parsed.data;
  const signalValue = MOOD_VALUE_MAP[mood];

  // Merge energyProfile without clobbering existing fields
  const existingProfile =
    member.energyProfile && typeof member.energyProfile === "object"
      ? (member.energyProfile as Record<string, unknown>)
      : {};

  const updatedProfile = {
    ...existingProfile,
    lastMood: mood,
    updatedAt: new Date().toISOString(),
  };

  await prisma.$transaction([
    prisma.behavioralSignal.create({
      data: {
        userId,
        tripId,
        signalType: "pace_signal",
        signalValue,
        rawAction: `mood_report:${mood}`,
        tripPhase: "active",
      },
    }),
    prisma.tripMember.update({
      where: { tripId_userId: { tripId, userId } },
      data: { energyProfile: updatedProfile },
    }),
  ]);

  return NextResponse.json({ success: true });
}
