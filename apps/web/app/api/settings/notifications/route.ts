/**
 * GET + PATCH /api/settings/notifications
 * Auth: session required, userId from session only
 * GET: returns notification preferences or Prisma defaults
 * PATCH: upserts single or multiple notification fields
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateNotificationsSchema } from "@/lib/validations/settings";
import { prisma } from "@/lib/prisma";

const NOTIF_SELECT = {
  tripReminders: true,
  morningBriefing: true,
  groupActivity: true,
  postTripPrompt: true,
  citySeeded: true,
  inspirationNudges: true,
  productUpdates: true,
} as const;

const DEFAULTS = {
  tripReminders: true,
  morningBriefing: true,
  groupActivity: true,
  postTripPrompt: true,
  citySeeded: true,
  inspirationNudges: false,
  productUpdates: false,
};

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  const notifs = await prisma.notificationPreference.findUnique({
    where: { userId },
    select: NOTIF_SELECT,
  });

  return NextResponse.json(notifs ?? DEFAULTS);
}

export async function PATCH(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const result = updateNotificationsSchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const updated = await prisma.notificationPreference.upsert({
    where: { userId },
    create: { userId, ...result.data },
    update: result.data,
    select: NOTIF_SELECT,
  });

  return NextResponse.json(updated);
}
