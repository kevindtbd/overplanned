/**
 * Route handler tests for POST /api/settings/billing-portal
 * Tests auth guards, missing Stripe customer, portal session creation,
 * URL validation, and error handling.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

vi.mock("@/lib/stripe", () => ({
  stripe: {
    billingPortal: {
      sessions: {
        create: vi.fn(),
      },
    },
  },
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { stripe } = await import("@/lib/stripe");
const { POST } = await import(
  "../../app/api/settings/billing-portal/route"
);

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);
const mockStripe = vi.mocked(stripe, true);

function makePostRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/billing-portal", {
    method: "POST",
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

// ---------------------------------------------------------------------------
// Auth guards
// ---------------------------------------------------------------------------
describe("POST /api/settings/billing-portal — auth guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when session is null", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await POST(makePostRequest());
    expect(res.status).toBe(401);
  });

  it("returns 401 when session has no user", async () => {
    mockGetServerSession.mockResolvedValueOnce({ user: null } as never);
    const res = await POST(makePostRequest());
    expect(res.status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// Missing Stripe customer
// ---------------------------------------------------------------------------
describe("POST /api/settings/billing-portal — no billing account", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 404 when user has no stripeCustomerId", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.findUnique.mockResolvedValueOnce(
      { stripeCustomerId: null } as never
    );

    const res = await POST(makePostRequest());
    expect(res.status).toBe(404);

    const json = await res.json();
    expect(json.error).toBe("No billing account found");
  });

  it("returns 404 when user record not found in DB", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.findUnique.mockResolvedValueOnce(null);

    const res = await POST(makePostRequest());
    expect(res.status).toBe(404);
  });
});

// ---------------------------------------------------------------------------
// Happy path — portal session creation
// ---------------------------------------------------------------------------
describe("POST /api/settings/billing-portal — happy path", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXTAUTH_URL = "http://localhost:3000";
  });

  it("creates portal session and returns URL", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.findUnique.mockResolvedValueOnce(
      { stripeCustomerId: "cus_test123" } as never
    );
    mockStripe.billingPortal.sessions.create.mockResolvedValueOnce(
      { url: "https://billing.stripe.com/session/test_abc" } as never
    );

    const res = await POST(makePostRequest());
    expect(res.status).toBe(200);

    const json = await res.json();
    expect(json.url).toBe("https://billing.stripe.com/session/test_abc");

    // Verify Stripe was called with correct customer and return_url
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const createCall = mockStripe.billingPortal.sessions.create.mock.calls[0]?.[0] as any;
    expect(createCall?.customer).toBe("cus_test123");
    expect(createCall?.return_url).toBe("http://localhost:3000/settings");
  });

  it("looks up stripeCustomerId from DB, not session", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.findUnique.mockResolvedValueOnce(
      { stripeCustomerId: "cus_db_lookup" } as never
    );
    mockStripe.billingPortal.sessions.create.mockResolvedValueOnce(
      { url: "https://billing.stripe.com/session/xyz" } as never
    );

    await POST(makePostRequest());

    // Verify DB lookup used session userId
    const findCall = mockPrisma.user.findUnique.mock.calls[0][0];
    expect(findCall.where).toEqual({ id: "user-abc" });
    expect(findCall.select).toEqual({ stripeCustomerId: true });
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------
describe("POST /api/settings/billing-portal — error handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.NEXTAUTH_URL = "http://localhost:3000";
  });

  it("returns 502 when portal session URL is invalid", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.findUnique.mockResolvedValueOnce(
      { stripeCustomerId: "cus_test123" } as never
    );
    mockStripe.billingPortal.sessions.create.mockResolvedValueOnce(
      { url: "https://evil.com/phishing" } as never
    );

    const res = await POST(makePostRequest());
    expect(res.status).toBe(502);

    const json = await res.json();
    expect(json.error).toBe("Failed to create billing session");
  });

  it("returns 500 when Stripe throws an error", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.user.findUnique.mockResolvedValueOnce(
      { stripeCustomerId: "cus_test123" } as never
    );
    mockStripe.billingPortal.sessions.create.mockRejectedValueOnce(
      new Error("Stripe API error")
    );

    const res = await POST(makePostRequest());
    expect(res.status).toBe(500);

    const json = await res.json();
    expect(json.error).toBe("Internal error");
  });
});
