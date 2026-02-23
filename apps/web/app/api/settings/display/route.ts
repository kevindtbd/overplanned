/**
 * GET + PATCH /api/settings/display
 * Auth: session required, userId from session only
 * GET: returns display preferences or defaults
 * PATCH: upserts display fields (units, formats, theme)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateDisplaySchema } from "@/lib/validations/settings";
import { prisma } from "@/lib/prisma";

const DISPLAY_SELECT = {
  distanceUnit: true,
  temperatureUnit: true,
  dateFormat: true,
  timeFormat: true,
  theme: true,
} as const;

const DEFAULTS = {
  distanceUnit: "mi",
  temperatureUnit: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
};

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  const display = await prisma.userPreference.findUnique({
    where: { userId },
    select: DISPLAY_SELECT,
  });

  return NextResponse.json(display ?? DEFAULTS);
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

  const result = updateDisplaySchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const updated = await prisma.userPreference.upsert({
    where: { userId },
    create: { userId, ...result.data },
    update: result.data,
    select: DISPLAY_SELECT,
  });

  return NextResponse.json(updated);
}
