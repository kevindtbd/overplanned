/**
 * Route handler tests for DELETE /api/settings/account
 * Tests auth, email confirmation, anonymization, and cascade deletion.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: { update: vi.fn() },
    $transaction: vi.fn(),
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { DELETE } = await import("../../app/api/settings/account/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma, true);

function makeDeleteRequest(body: unknown): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/account", {
    method: "DELETE",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };

describe("DELETE /api/settings/account — auth", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 401 when no session", async () => {
    mockGetServerSession.mockResolvedValueOnce(null);
    const res = await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));
    expect(res.status).toBe(401);
  });
});

describe("DELETE /api/settings/account — validation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns 400 when confirmEmail is missing", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await DELETE(makeDeleteRequest({}));
    expect(res.status).toBe(400);
  });

  it("returns 400 when confirmEmail is not a valid email", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await DELETE(makeDeleteRequest({ confirmEmail: "not-an-email" }));
    expect(res.status).toBe(400);
  });

  it("returns 403 when confirmEmail does not match session email", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    const res = await DELETE(makeDeleteRequest({ confirmEmail: "wrong@example.com" }));
    expect(res.status).toBe(403);
    const json = await res.json();
    expect(json.error).toBe("Email does not match");
  });

  it("matches email case-insensitively", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    const res = await DELETE(makeDeleteRequest({ confirmEmail: "TEST@EXAMPLE.COM" }));
    expect(res.status).toBe(200);
  });
});

describe("DELETE /api/settings/account — deletion", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns { deleted: true } on success", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    const res = await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ deleted: true });
  });

  it("calls $transaction with a callback function", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockResolvedValueOnce(undefined as never);

    await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));

    expect(mockPrisma.$transaction).toHaveBeenCalledTimes(1);
    const txArg = mockPrisma.$transaction.mock.calls[0][0];
    expect(typeof txArg).toBe("function");
  });

  it("anonymizes orphan tables with session userId then deletes user", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);

    const mockTx = {
      trip: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      behavioralSignal: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      intentionSignal: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      rawEvent: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      personaDimension: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      rankingEvent: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      auditLog: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      sharedTripToken: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      inviteToken: { updateMany: vi.fn().mockResolvedValue({ count: 0 }) },
      user: { delete: vi.fn().mockResolvedValue({}) },
    };

    mockPrisma.$transaction.mockImplementationOnce((async (cb: (tx: typeof mockTx) => Promise<void>) => {
      await cb(mockTx);
    }) as never);

    await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));

    // Verify all 6 orphan tables anonymized
    expect(mockTx.trip.updateMany).toHaveBeenCalledWith({
      where: { userId: "user-abc" },
      data: { userId: "DELETED" },
    });
    expect(mockTx.behavioralSignal.updateMany).toHaveBeenCalledWith({
      where: { userId: "user-abc" },
      data: { userId: "DELETED" },
    });
    expect(mockTx.intentionSignal.updateMany).toHaveBeenCalledWith({
      where: { userId: "user-abc" },
      data: { userId: "DELETED" },
    });
    expect(mockTx.rawEvent.updateMany).toHaveBeenCalledWith({
      where: { userId: "user-abc" },
      data: { userId: "DELETED" },
    });
    expect(mockTx.personaDimension.updateMany).toHaveBeenCalledWith({
      where: { userId: "user-abc" },
      data: { userId: "DELETED" },
    });
    expect(mockTx.rankingEvent.updateMany).toHaveBeenCalledWith({
      where: { userId: "user-abc" },
      data: { userId: "DELETED" },
    });

    // Verify 3 bare string refs anonymized
    expect(mockTx.auditLog.updateMany).toHaveBeenCalledWith({
      where: { actorId: "user-abc" },
      data: { actorId: "DELETED" },
    });
    expect(mockTx.sharedTripToken.updateMany).toHaveBeenCalledWith({
      where: { createdBy: "user-abc" },
      data: { createdBy: "DELETED" },
    });
    expect(mockTx.inviteToken.updateMany).toHaveBeenCalledWith({
      where: { createdBy: "user-abc" },
      data: { createdBy: "DELETED" },
    });

    // Verify user deletion
    expect(mockTx.user.delete).toHaveBeenCalledWith({
      where: { id: "user-abc" },
    });
  });

  it("returns 500 on transaction failure", async () => {
    mockGetServerSession.mockResolvedValueOnce(authedSession as never);
    mockPrisma.$transaction.mockRejectedValueOnce(new Error("DB error"));

    const res = await DELETE(makeDeleteRequest({ confirmEmail: "test@example.com" }));
    expect(res.status).toBe(500);
    const json = await res.json();
    expect(json.error).toBe("Failed to delete account");
  });
});
