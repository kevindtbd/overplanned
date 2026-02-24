/**
 * GET  /api/trips/[id]/expenses — List expenses for a trip
 * POST /api/trips/[id]/expenses — Create a new expense
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { expenseCreateSchema } from "@/lib/validations/expenses";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId } = params;

  try {
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    const expenses = await prisma.expense.findMany({
      where: { tripId },
      orderBy: { createdAt: "desc" },
      include: {
        paidBy: {
          select: { id: true, name: true, avatarUrl: true },
        },
      },
    });

    return NextResponse.json({ expenses }, { status: 200 });
  } catch (err) {
    console.error(`[GET /api/trips/${tripId}/expenses] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
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

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const parsed = expenseCreateSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Validation failed", details: parsed.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  const { description, amountCents, splitWith, slotId } = parsed.data;

  try {
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    // Deduplicate splitWith
    const deduped = splitWith ? [...new Set(splitWith)] : [];

    // Validate splitWith members are all joined trip members
    if (deduped.length > 0) {
      const validMembers = await prisma.tripMember.findMany({
        where: { tripId, userId: { in: deduped }, status: "joined" },
        select: { userId: true },
      });

      if (validMembers.length !== deduped.length) {
        return NextResponse.json(
          { error: "Some split members are not joined trip members" },
          { status: 400 }
        );
      }
    }

    // Validate slotId belongs to the same trip
    if (slotId) {
      const slot = await prisma.itinerarySlot.findFirst({
        where: { id: slotId, tripId },
      });

      if (!slot) {
        return NextResponse.json(
          { error: "Slot not found in this trip" },
          { status: 400 }
        );
      }
    }

    const expense = await prisma.expense.create({
      data: {
        tripId,
        paidById: userId,
        description,
        amountCents,
        splitWith: deduped,
        slotId: slotId || null,
      },
      include: {
        paidBy: {
          select: { id: true, name: true, avatarUrl: true },
        },
      },
    });

    return NextResponse.json({ expense }, { status: 201 });
  } catch (err) {
    console.error(`[POST /api/trips/${tripId}/expenses] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
