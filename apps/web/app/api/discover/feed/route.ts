/**
 * GET /api/discover/feed
 *
 * Returns ActivityNodes for the discover surface.
 * Filters by city and optional category.
 * Returns only approved nodes with images, sorted by convergenceScore desc.
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = req.nextUrl;
  const city = searchParams.get("city");
  const category = searchParams.get("category") ?? undefined;
  const limit = Math.min(parseInt(searchParams.get("limit") ?? "60", 10), 100);

  if (!city) {
    return NextResponse.json(
      { error: "city parameter is required" },
      { status: 400 }
    );
  }

  const whereClause: Record<string, unknown> = {
    status: "approved",
    city: { equals: city, mode: "insensitive" },
  };

  if (category) {
    whereClause.category = category;
  }

  try {
    const nodes = await prisma.activityNode.findMany({
      where: whereClause,
      take: limit,
      orderBy: [
        { convergenceScore: "desc" },
        { authorityScore: "desc" },
      ],
      select: {
        id: true,
        name: true,
        city: true,
        category: true,
        subcategory: true,
        priceLevel: true,
        convergenceScore: true,
        authorityScore: true,
        descriptionShort: true,
        primaryImageUrl: true,
        neighborhood: true,
        vibeTags: {
          select: {
            score: true,
            vibeTag: {
              select: {
                slug: true,
                name: true,
              },
            },
          },
          orderBy: { score: "desc" },
          take: 5,
        },
      },
    });

    // Reshape vibeTags for client consumption
    const shaped = nodes.map((n) => ({
      id: n.id,
      name: n.name,
      city: n.city,
      category: n.category,
      subcategory: n.subcategory,
      priceLevel: n.priceLevel,
      convergenceScore: n.convergenceScore,
      authorityScore: n.authorityScore,
      descriptionShort: n.descriptionShort,
      primaryImageUrl: n.primaryImageUrl,
      neighborhood: n.neighborhood,
      vibeTags: n.vibeTags.map((vt) => ({
        slug: vt.vibeTag.slug,
        name: vt.vibeTag.name,
        score: vt.score,
      })),
    }));

    return NextResponse.json({ nodes: shaped });
  } catch (err) {
    console.error("[discover/feed] DB error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
