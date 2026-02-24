/**
 * GET /api/explore/vibes?key=warm_slow
 *
 * Returns up to 3 cities that match a vibe archetype, sorted by score descending.
 * Readiness gate: nodeCount >= 25, catCount >= 4.
 * Auth required.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { VIBE_ARCHETYPES, type VibeKey } from "@/lib/vibes";

const VALID_VIBE_KEYS = new Set(Object.keys(VIBE_ARCHETYPES));

/** Minimum approved nodes to recommend a city */
const MIN_NODE_COUNT = 25;

/** Minimum distinct categories to recommend a city */
const MIN_CAT_COUNT = 4;

/** Maximum cities returned per vibe query */
const MAX_RESULTS = 3;

export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = req.nextUrl;
  const key = searchParams.get("key");

  if (!key || !VALID_VIBE_KEYS.has(key)) {
    return NextResponse.json(
      {
        error: "Invalid vibe key",
        valid: Array.from(VALID_VIBE_KEYS),
      },
      { status: 400 }
    );
  }

  try {
    const profiles = await prisma.cityVibeProfile.findMany({
      where: {
        vibeKey: key as VibeKey,
        nodeCount: { gte: MIN_NODE_COUNT },
        catCount: { gte: MIN_CAT_COUNT },
      },
      orderBy: { score: "desc" },
      take: MAX_RESULTS,
      select: {
        city: true,
        country: true,
        score: true,
        imageUrl: true,
        tagline: true,
        nodeCount: true,
      },
    });

    return NextResponse.json({ cities: profiles });
  } catch (err) {
    console.error("[explore/vibes] DB error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
