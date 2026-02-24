import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";

/** Extract authenticated user ID or return 401 response */
export async function requireAuth(): Promise<{ userId: string } | NextResponse> {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  return { userId: (session.user as { id: string }).id };
}

/** Check trip membership, return 404 if not a joined member */
export async function requireTripMember(
  tripId: string,
  userId: string
): Promise<{ role: string } | NextResponse> {
  const membership = await prisma.tripMember.findUnique({
    where: { tripId_userId: { tripId, userId } },
    select: { status: true, role: true },
  });
  if (!membership || membership.status !== "joined") {
    return NextResponse.json({ error: "Trip not found" }, { status: 404 });
  }
  return { role: membership.role };
}

/** Parse JSON body with error handling */
export async function parseBody<T>(req: Request): Promise<T | NextResponse> {
  try {
    return (await req.json()) as T;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
}

/** Standard error response */
export function apiError(status: number, message: string, details?: unknown) {
  return NextResponse.json(
    { error: message, ...(details ? { details } : {}) },
    { status }
  );
}
