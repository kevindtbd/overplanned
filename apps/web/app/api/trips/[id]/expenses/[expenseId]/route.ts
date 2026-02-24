/**
 * DELETE /api/trips/[id]/expenses/[expenseId] — Delete an expense (author only)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string; expenseId: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId, expenseId } = params;

  try {
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    // Triple-condition: expense must exist, belong to this trip, and be paid by this user
    const expense = await prisma.expense.findFirst({
      where: { id: expenseId, tripId, paidById: userId },
    });

    if (!expense) {
      return NextResponse.json({ error: "Expense not found" }, { status: 404 });
    }

    // Audit log + delete
    await prisma.auditLog.create({
      data: {
        actorId: userId,
        action: "expense_delete",
        targetType: "Expense",
        targetId: expenseId,
        before: expense as unknown as import("@prisma/client").Prisma.InputJsonValue,
        ipAddress:
          req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown",
        userAgent: req.headers.get("user-agent") || "unknown",
      },
    });

    await prisma.expense.delete({ where: { id: expenseId } });

    return NextResponse.json({ deleted: true }, { status: 200 });
  } catch (err) {
    console.error(
      `[DELETE /api/trips/${tripId}/expenses/${expenseId}] Error:`,
      err
    );
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
