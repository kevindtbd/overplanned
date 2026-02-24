import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import { rateLimit, rateLimitPresets } from "@/lib/rate-limit";

export async function POST(req: NextRequest) {
  // Rate limit: 10 attempts per minute per IP
  const limited = rateLimit(req, rateLimitPresets.authenticated);
  if (limited) return limited;

  // No beta gate configured — allow through
  const betaCode = process.env.BETA_CODE;
  if (!betaCode) {
    return NextResponse.json({ valid: true });
  }

  let body: { code?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const code = body.code?.trim();
  if (!code) {
    return NextResponse.json({ error: "Code required" }, { status: 400 });
  }

  // Timing-safe comparison to prevent timing attacks
  const codeBuffer = Buffer.from(code);
  const betaBuffer = Buffer.from(betaCode);

  if (
    codeBuffer.length !== betaBuffer.length ||
    !crypto.timingSafeEqual(codeBuffer, betaBuffer)
  ) {
    return NextResponse.json({ error: "Invalid beta code" }, { status: 401 });
  }

  return NextResponse.json({ valid: true });
}
