/**
 * GET + PATCH /api/settings/preferences
 * Auth: session required, userId from session only
 * GET: returns user preferences or defaults
 * PATCH: upserts preferences with array deduplication
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updatePreferencesSchema } from "@/lib/validations/settings";
import { prisma } from "@/lib/prisma";

const PREF_SELECT = {
  dietary: true,
  mobility: true,
  languages: true,
  travelFrequency: true,
  vibePreferences: true,
  travelStyleNote: true,
  budgetComfort: true,
  spendingPriorities: true,
  accommodationTypes: true,
  transitModes: true,
  preferencesNote: true,
} as const;

const DEFAULTS = {
  dietary: [] as string[],
  mobility: [] as string[],
  languages: [] as string[],
  travelFrequency: null as string | null,
  vibePreferences: [] as string[],
  travelStyleNote: null as string | null,
  budgetComfort: null as string | null,
  spendingPriorities: [] as string[],
  accommodationTypes: [] as string[],
  transitModes: [] as string[],
  preferencesNote: null as string | null,
};

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  const prefs = await prisma.userPreference.findUnique({
    where: { userId },
    select: PREF_SELECT,
  });

  return NextResponse.json(prefs ?? DEFAULTS);
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

  const result = updatePreferencesSchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  // Server-side array deduplication + scalar pass-through
  const data: Record<string, unknown> = {};
  if (result.data.dietary !== undefined) {
    data.dietary = [...new Set(result.data.dietary)];
  }
  if (result.data.mobility !== undefined) {
    data.mobility = [...new Set(result.data.mobility)];
  }
  if (result.data.languages !== undefined) {
    data.languages = [...new Set(result.data.languages)];
  }
  if (result.data.travelFrequency !== undefined) {
    data.travelFrequency = result.data.travelFrequency;
  }
  if (result.data.vibePreferences !== undefined) {
    data.vibePreferences = [...new Set(result.data.vibePreferences)];
  }
  if (result.data.travelStyleNote !== undefined) {
    data.travelStyleNote = result.data.travelStyleNote;
  }
  if (result.data.budgetComfort !== undefined) {
    data.budgetComfort = result.data.budgetComfort;
  }
  if (result.data.spendingPriorities !== undefined) {
    data.spendingPriorities = [...new Set(result.data.spendingPriorities)];
  }
  if (result.data.accommodationTypes !== undefined) {
    data.accommodationTypes = [...new Set(result.data.accommodationTypes)];
  }
  if (result.data.transitModes !== undefined) {
    data.transitModes = [...new Set(result.data.transitModes)];
  }
  if (result.data.preferencesNote !== undefined) {
    // Normalize empty string to null
    const trimmed = result.data.preferencesNote.trim();
    data.preferencesNote = trimmed === "" ? null : trimmed;
  }

  const updated = await prisma.userPreference.upsert({
    where: { userId },
    create: {
      userId,
      dietary: (data.dietary as string[]) ?? [],
      mobility: (data.mobility as string[]) ?? [],
      languages: (data.languages as string[]) ?? [],
      travelFrequency: (data.travelFrequency as string | null) ?? null,
      vibePreferences: (data.vibePreferences as string[]) ?? [],
      travelStyleNote: (data.travelStyleNote as string | null) ?? null,
      budgetComfort: (data.budgetComfort as string | null) ?? null,
      spendingPriorities: (data.spendingPriorities as string[]) ?? [],
      accommodationTypes: (data.accommodationTypes as string[]) ?? [],
      transitModes: (data.transitModes as string[]) ?? [],
      preferencesNote: (data.preferencesNote as string | null) ?? null,
    },
    update: data,
    select: PREF_SELECT,
  });

  return NextResponse.json(updated);
}
