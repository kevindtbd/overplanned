/**
 * POST  /api/trips/[id]/packing — Generate packing list via LLM
 * PATCH /api/trips/[id]/packing — Toggle check state on a packing item
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { rateLimit, rateLimitPresets } from "@/lib/rate-limit";
import {
  packingGenerateSchema,
  packingCheckSchema,
  packingListSchema,
} from "@/lib/validations/packing";
import Anthropic from "@anthropic-ai/sdk";
import crypto from "crypto";

const anthropic = new Anthropic();

// Sanitize string for LLM prompt — strip control chars and limit length
function sanitize(input: string, maxLen = 200): string {
  return input
    .replace(/[\x00-\x1f\x7f]/g, "")
    .replace(/<[^>]*>/g, "")
    .trim()
    .slice(0, maxLen);
}

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

  // Rate limit: LLM tier (3 req/hour by userId)
  const rateLimited = rateLimit(req, rateLimitPresets.llm, `packing:${userId}`);
  if (rateLimited) return rateLimited;

  // Parse optional body
  let body: unknown = undefined;
  try {
    const text = await req.text();
    if (text.trim()) {
      body = JSON.parse(text);
    }
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = packingGenerateSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const regenerate = parsed.data?.regenerate ?? false;

  try {
    // Auth: verify membership
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { role: true, status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    // Fetch trip with legs for destination context
    const trip = await prisma.trip.findUnique({
      where: { id: tripId },
      select: {
        id: true,
        packingList: true,
        startDate: true,
        endDate: true,
        presetTemplate: true,
        personaSeed: true,
        legs: {
          orderBy: { position: "asc" },
          select: {
            destination: true,
            city: true,
            country: true,
          },
        },
      },
    });

    if (!trip) {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    // If list exists and not regenerating, return existing
    if (trip.packingList && !regenerate) {
      return NextResponse.json({ packingList: trip.packingList }, { status: 200 });
    }

    // Build LLM prompt inputs from trip data
    const primaryLeg = trip.legs[0];
    if (!primaryLeg) {
      return NextResponse.json(
        { error: "Trip has no destination legs" },
        { status: 400 }
      );
    }

    const destination = sanitize(primaryLeg.destination);
    const city = sanitize(primaryLeg.city);
    const country = sanitize(primaryLeg.country);
    const startDate = trip.startDate.toISOString().split("T")[0];
    const endDate = trip.endDate.toISOString().split("T")[0];
    const durationDays = Math.ceil(
      (trip.endDate.getTime() - trip.startDate.getTime()) / (1000 * 60 * 60 * 24)
    );
    const template = trip.presetTemplate ? sanitize(trip.presetTemplate, 100) : "general";

    const personaSeed = trip.personaSeed as Record<string, unknown> | null;
    const pace = personaSeed?.pace
      ? sanitize(String(personaSeed.pace), 50)
      : "moderate";

    const response = await anthropic.messages.create({
      model: "claude-haiku-4-5-20251001",
      max_tokens: 800,
      temperature: 0.4,
      system: `You are a travel packing assistant. Generate a packing list for a trip. Return ONLY valid JSON matching this exact schema:
{
  "items": [
    { "id": "1", "text": "Item name", "category": "essentials|clothing|documents|tech|toiletries|misc", "checked": false }
  ]
}

Rules:
- Maximum 30 items
- Each item text max 100 characters
- Categories must be one of: essentials, clothing, documents, tech, toiletries, misc
- Item IDs should be simple sequential strings ("1", "2", etc.) — they will be replaced with UUIDs
- Focus on practical, destination-appropriate items
- Consider weather, culture, and trip duration`,
      messages: [
        {
          role: "user",
          content: `Destination: ${destination} (${city}, ${country})
Dates: ${startDate} to ${endDate} (${durationDays} days)
Trip style: ${template}
Pace: ${pace}

Generate a packing list for this trip.`,
        },
      ],
    });

    const textContent = response.content.find((c) => c.type === "text");
    if (!textContent || textContent.type !== "text") {
      return NextResponse.json(
        { error: "LLM returned no text content" },
        { status: 502 }
      );
    }

    // Parse and validate LLM output
    let llmOutput: unknown;
    try {
      llmOutput = JSON.parse(textContent.text);
    } catch {
      console.error("[packing] Failed to parse LLM JSON response");
      return NextResponse.json(
        { error: "LLM returned invalid JSON" },
        { status: 502 }
      );
    }

    const validated = packingListSchema.safeParse(llmOutput);
    if (!validated.success) {
      console.error("[packing] LLM output failed validation:", validated.error.flatten());
      return NextResponse.json(
        { error: "LLM returned invalid packing list format" },
        { status: 502 }
      );
    }

    // Cap at 30 items, assign UUIDs
    const items = validated.data.items.slice(0, 30).map((item) => ({
      ...item,
      id: crypto.randomUUID(),
      checked: false,
    }));

    const packingList = {
      items,
      generatedAt: new Date().toISOString(),
      model: "claude-haiku-4-5-20251001",
    };

    // Store in Trip.packingList JSONB
    await prisma.trip.update({
      where: { id: tripId },
      data: { packingList: packingList as unknown as Record<string, unknown> },
    });

    console.log(
      `[packing] tripId=${tripId} generated ${items.length} items regenerate=${regenerate}`
    );

    return NextResponse.json({ packingList }, { status: 200 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/packing] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = packingCheckSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const { itemId, checked } = parsed.data;

  try {
    // Auth: verify membership
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { role: true, status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    const trip = await prisma.trip.findUnique({
      where: { id: tripId },
      select: { packingList: true },
    });

    if (!trip || !trip.packingList) {
      return NextResponse.json(
        { error: "No packing list exists for this trip" },
        { status: 404 }
      );
    }

    const packingList = trip.packingList as {
      items: Array<{ id: string; text: string; category: string; checked: boolean }>;
      generatedAt: string;
      model: string;
    };

    // Find and update the item
    const itemIndex = packingList.items.findIndex((item) => item.id === itemId);
    if (itemIndex === -1) {
      return NextResponse.json({ error: "Item not found" }, { status: 404 });
    }

    packingList.items[itemIndex].checked = checked;

    // Atomic update: write packingList + log signal
    await prisma.$transaction([
      prisma.trip.update({
        where: { id: tripId },
        data: { packingList: packingList as unknown as Record<string, unknown> },
      }),
      prisma.behavioralSignal.create({
        data: {
          userId,
          tripId,
          signalType: checked ? "packing_checked" : "packing_unchecked",
          signalValue: checked ? 1.0 : -1.0,
          metadata: { itemId, itemText: packingList.items[itemIndex].text },
        },
      }),
    ]);

    return NextResponse.json({ packingList }, { status: 200 });
  } catch (err) {
    console.error(`[PATCH /api/trips/${tripId}/packing] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
