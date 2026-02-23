/**
 * PATCH /api/settings/account — Update display name
 * Auth: session required, userId from session only
 * Whitelist: only `name` field is writable
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { updateAccountSchema } from "@/lib/validations/settings";
import { prisma } from "@/lib/prisma";

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
