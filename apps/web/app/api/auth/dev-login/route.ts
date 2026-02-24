/**
 * POST /api/auth/dev-login — Dev-only login bypass
 *
 * Creates a real NextAuth database session for any existing user,
 * skipping Google OAuth. Only available in development.
 *
 * SECURITY: Three layers prevent production exposure:
 * 1. Build-time: throws at import if NODE_ENV !== development
 * 2. Runtime: early return 404 if NODE_ENV !== development
 * 3. UI: sign-in page only renders dev buttons in development
 *
 * Body: { email: string }
 * Sets: next-auth.session-token cookie
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { v4 as uuidv4 } from "uuid";

const IS_DEV = process.env.NODE_ENV === "development";

export async function POST(req: NextRequest) {
  // Runtime guard — only available in development.
  // Returns a bare 404 with no body so it is indistinguishable from
  // a non-existent route (defense-in-depth alongside the middleware block).
  if (!IS_DEV) {
    return new NextResponse(null, { status: 404 });
  }

  let body: { email?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const email = body.email?.trim().toLowerCase();
  if (!email) {
    return NextResponse.json({ error: "Email required" }, { status: 400 });
  }

  const user = await prisma.user.findUnique({ where: { email } });
  if (!user) {
    return NextResponse.json(
      { error: `No user found with email: ${email}` },
      { status: 404 }
    );
  }

  // Create a real NextAuth database session
  const sessionToken = uuidv4();
  const expires = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000); // 30 days

  await prisma.session.create({
    data: {
      sessionToken,
      userId: user.id,
      expires,
    },
  });

  // Set the session cookie (non-HTTPS in dev = no __Secure- prefix)
  const res = NextResponse.json({
    ok: true,
    user: { id: user.id, email: user.email, name: user.name },
  });

  res.cookies.set("next-auth.session-token", sessionToken, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    expires,
  });

  return res;
}
