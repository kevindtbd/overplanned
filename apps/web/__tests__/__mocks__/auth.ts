import { vi } from "vitest";

export interface MockUser {
  id: string;
  email: string;
  name: string;
  subscriptionTier: string;
  systemRole: string;
}

const defaultUser: MockUser = {
  id: "test-user-id",
  email: "test@example.com",
  name: "Test User",
  subscriptionTier: "beta",
  systemRole: "user",
};

export function mockSession(user: Partial<MockUser> = {}) {
  const sessionUser = { ...defaultUser, ...user };
  vi.mock("next-auth", async () => {
    const actual = await vi.importActual("next-auth");
    return {
      ...actual,
      getServerSession: vi.fn(() =>
        Promise.resolve({ user: sessionUser, expires: "2099-01-01" })
      ),
    };
  });
  return sessionUser;
}

export function mockNoSession() {
  vi.mock("next-auth", async () => {
    const actual = await vi.importActual("next-auth");
    return {
      ...actual,
      getServerSession: vi.fn(() => Promise.resolve(null)),
    };
  });
}
