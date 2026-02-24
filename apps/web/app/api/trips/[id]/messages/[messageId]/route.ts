/**
 * DELETE /api/trips/[id]/messages/[messageId] — Delete own message
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string; messageId: string } }
) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const { id: tripId, messageId } = params;

  try {
    // Membership check
    const membership = await prisma.tripMember.findUnique({
      where: { tripId_userId: { tripId, userId } },
      select: { status: true },
    });

    if (!membership || membership.status !== "joined") {
      return NextResponse.json({ error: "Trip not found" }, { status: 404 });
    }

    // Find message with triple-condition: correct id, trip, and author
    const message = await prisma.message.findFirst({
      where: { id: messageId, tripId, userId },
    });

    if (!message) {
      return NextResponse.json({ error: "Message not found" }, { status: 404 });
    }

    await prisma.message.delete({ where: { id: messageId } });

    return NextResponse.json({ success: true }, { status: 200 });
  } catch (err) {
    console.error(`[DELETE /api/trips/${tripId}/messages/${messageId}] Error:`, err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
