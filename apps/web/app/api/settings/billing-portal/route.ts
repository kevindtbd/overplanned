/**
 * POST /api/settings/billing-portal
 * Auth: session required
 * Creates a Stripe Customer Portal session and returns the URL.
 * Looks up stripeCustomerId from DB (never from session).
 */

import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth/config";
import { prisma } from "@/lib/prisma";
import { stripe } from "@/lib/stripe";

export async function POST(_req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const userId = (session.user as { id: string }).id;

  const dbUser = await prisma.user.findUnique({
    where: { id: userId },
    select: { stripeCustomerId: true },
  });

  if (!dbUser?.stripeCustomerId) {
    return NextResponse.json({ error: "No billing account found" }, { status: 404 });
  }

  try {
    const portalSession = await stripe.billingPortal.sessions.create({
      customer: dbUser.stripeCustomerId,
      return_url: `${process.env.NEXTAUTH_URL}/settings`,
    });

    if (!portalSession.url || !portalSession.url.startsWith("https://billing.stripe.com/")) {
      return NextResponse.json({ error: "Failed to create billing session" }, { status: 502 });
    }

    return NextResponse.json({ url: portalSession.url });
  } catch (err) {
    console.error("[billing-portal] Error:", err);
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
