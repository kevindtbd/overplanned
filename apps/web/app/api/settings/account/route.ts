/**
 * PATCH /api/settings/account — Update display name
 * Auth: session required, userId from session only
 * Whitelist: only `name` field is writable
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateAccountSchema, deleteAccountSchema } from "@/lib/validations/settings";
import { prisma, TransactionClient } from "@/lib/prisma";

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

  const result = updateAccountSchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  // Whitelist: only update name, nothing else from the body
  const updated = await prisma.user.update({
    where: { id: userId },
    data: { name: result.data.name },
    select: { name: true },
  });

  return NextResponse.json(updated);
}

export async function DELETE(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;
  const userEmail = (session.user as { email: string }).email;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const result = deleteAccountSchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  // Case-insensitive email match
  if (result.data.confirmEmail.toLowerCase() !== userEmail.toLowerCase()) {
    return NextResponse.json({ error: "Email does not match" }, { status: 403 });
  }

  try {
    await prisma.$transaction(async (tx: TransactionClient) => {
      // Step 1: Anonymize 6 orphan tables (no FK cascade)
      await tx.trip.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.behavioralSignal.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.intentionSignal.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.rawEvent.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.personaDimension.updateMany({ where: { userId }, data: { userId: "DELETED" } });
      await tx.rankingEvent.updateMany({ where: { userId }, data: { userId: "DELETED" } });

      // Step 2: Anonymize bare string refs
      await tx.auditLog.updateMany({ where: { actorId: userId }, data: { actorId: "DELETED" } });
      await tx.sharedTripToken.updateMany({ where: { createdBy: userId }, data: { createdBy: "DELETED" } });
      await tx.inviteToken.updateMany({ where: { createdBy: userId }, data: { createdBy: "DELETED" } });

      // Step 3: Delete User row (cascade handles Session, Account, TripMember,
      // UserPreference, NotificationPreference, DataConsent, BackfillTrip, BackfillSignal, PersonaDelta)
      await tx.user.delete({ where: { id: userId } });
    });

    return NextResponse.json({ deleted: true });
  } catch {
    return NextResponse.json({ error: "Failed to delete account" }, { status: 500 });
  }
}
