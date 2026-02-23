/**
 * GET + PATCH /api/settings/privacy
 * Auth: session required, userId from session only
 * GET: returns consent preferences or GDPR-safe defaults (both false)
 * PATCH: upserts consent fields + creates AuditLog entry (GDPR Article 7)
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateConsentSchema } from "@/lib/validations/settings";
import { prisma } from "@/lib/prisma";

const CONSENT_SELECT = {
  modelTraining: true,
  anonymizedResearch: true,
} as const;

const DEFAULTS = {
  modelTraining: false,
  anonymizedResearch: false,
};

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  const consent = await prisma.dataConsent.findUnique({
    where: { userId },
    select: CONSENT_SELECT,
  });

  return NextResponse.json(consent ?? DEFAULTS);
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

  const result = updateConsentSchema.safeParse(body);
  if (!result.success) {
    return NextResponse.json(
      { error: "Validation failed", details: result.error.flatten().fieldErrors },
      { status: 400 }
    );
  }

  // Read current values for audit log (before)
  const before = await prisma.dataConsent.findUnique({
    where: { userId },
    select: CONSENT_SELECT,
  });

  const updated = await prisma.dataConsent.upsert({
    where: { userId },
    create: { userId, ...result.data },
    update: result.data,
    select: CONSENT_SELECT,
  });

  // Audit log: consent change (GDPR Article 7)
  await prisma.auditLog.create({
    data: {
      actorId: userId,
      action: "consent_update",
      targetType: "DataConsent",
      targetId: userId,
      before: before ?? DEFAULTS,
      after: updated,
      ipAddress: req.headers.get("x-forwarded-for") ?? "unknown",
      userAgent: req.headers.get("user-agent") ?? "unknown",
    },
  });

  return NextResponse.json(updated);
}
