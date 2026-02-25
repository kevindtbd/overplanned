import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SettingsPage from "@/app/settings/page";

// Mock Next.js modules
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("next/image", () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img src={src} alt={alt} />
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings",
  useRouter: () => ({
    refresh: vi.fn(),
    push: vi.fn(),
    replace: vi.fn(),
  }),
}));

// Mock AppShell
vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// Mock section components so we don't need fetch mocks for them
vi.mock("@/components/settings/TravelStyleSection", () => ({
  TravelStyleSection: () => <section><h2>Travel Style</h2></section>,
}));

vi.mock("@/components/settings/NotificationsSection", () => ({
  NotificationsSection: () => <section><h2>Notifications</h2></section>,
}));

vi.mock("@/components/settings/DisplayPreferences", () => ({
  DisplayPreferences: () => <section><h2>Display Preferences</h2></section>,
}));

vi.mock("@/components/settings/PrivacySection", () => ({
  PrivacySection: () => <section><h2>Privacy & Data</h2></section>,
}));

// Mock next-auth
const mockUseSession = vi.fn();
vi.mock("next-auth/react", () => ({
  useSession: () => mockUseSession(),
  signOut: vi.fn(),
}));

const authenticatedSession = {
  data: {
    user: {
      id: "user-123",
      name: "Kevin",
      email: "kevin@example.com",
      subscriptionTier: "beta",
      systemRole: "user",
    },
  },
  status: "authenticated" as const,
};

const loadingSession = {
  data: null,
  status: "loading" as const,
};

const unauthenticatedSession = {
  data: null,
  status: "unauthenticated" as const,
};

describe("SettingsPage — loading state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading state while session is loading", () => {
    mockUseSession.mockReturnValue(loadingSession);
    render(<SettingsPage />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
    // Should NOT show account section content while loading
    expect(screen.queryByText("Account")).not.toBeInTheDocument();
    expect(screen.queryByText("Sign out")).not.toBeInTheDocument();
  });
});

describe("SettingsPage — unauthenticated", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows error state when not signed in", () => {
    mockUseSession.mockReturnValue(unauthenticatedSession);
    render(<SettingsPage />);
    expect(screen.getByText("You need to be signed in to view settings.")).toBeInTheDocument();
  });
});

describe("SettingsPage — authenticated", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSession.mockReturnValue(authenticatedSession);
  });

  it("renders page header", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByText("Account, preferences, and privacy")).toBeInTheDocument();
  });

  it("renders Account section with user data", () => {
    render(<SettingsPage />);
    // "Account" appears in both anchor nav and section heading — use heading role
    expect(screen.getByRole("heading", { name: "Account" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("Kevin")).toBeInTheDocument();
    expect(screen.getByText("kevin@example.com")).toBeInTheDocument();
    expect(screen.getByText("google")).toBeInTheDocument();
    expect(screen.getByText("Sign out")).toBeInTheDocument();
  });

  it("renders Subscription badge with tier", () => {
    render(<SettingsPage />);
    // "Subscription" appears in both anchor nav and section heading — use heading role
    expect(screen.getByRole("heading", { name: "Subscription" })).toBeInTheDocument();
    // "Beta" appears in SubscriptionBadge and AboutSection version — use getAllByText
    const betaElements = screen.getAllByText("Beta");
    expect(betaElements.length).toBeGreaterThanOrEqual(1);
  });

  it("renders all stub sections", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Display Preferences")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Travel Style" })).toBeInTheDocument();
    // "Notifications" heading
    expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByText("Privacy & Data")).toBeInTheDocument();
    // "About" heading
    expect(screen.getByRole("heading", { name: "About" })).toBeInTheDocument();
  });

  it("does NOT render a delete account button", () => {
    render(<SettingsPage />);
    expect(screen.queryByText(/delete account/i)).not.toBeInTheDocument();
  });
});

describe("SettingsPage — AccountSection interaction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSession.mockReturnValue(authenticatedSession);
    global.fetch = vi.fn();
  });

  it("calls PATCH on blur with updated name", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ name: "New Name" }),
    });

    render(<SettingsPage />);
    const input = screen.getByDisplayValue("Kevin");

    await user.click(input); // focus it
    fireEvent.change(input, { target: { value: "New Name" } });
    await user.tab(); // trigger blur

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/settings/account",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ name: "New Name" }),
        })
      );
    });
  });

  it("reverts name on PATCH failure", async () => {
    const user = userEvent.setup();
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    render(<SettingsPage />);
    const input = screen.getByDisplayValue("Kevin");

    await user.click(input); // focus it
    fireEvent.change(input, { target: { value: "Will Fail" } });
    await user.tab();

    await waitFor(() => {
      expect(screen.getByDisplayValue("Kevin")).toBeInTheDocument();
    });
  });

  it("does not call PATCH when name is unchanged", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);
    const input = screen.getByDisplayValue("Kevin");

    await user.click(input);
    await user.tab(); // blur without changing

    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("calls signOut when sign out button is clicked", async () => {
    const user = userEvent.setup();
    const { signOut } = await import("next-auth/react");
    render(<SettingsPage />);

    await user.click(screen.getByText("Sign out"));
    expect(signOut).toHaveBeenCalledWith({ callbackUrl: "/" });
  });
});
