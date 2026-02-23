/**
 * Component tests for SubscriptionBadge
 * Tests tier label rendering, billing button visibility,
 * billing flow (POST + redirect), loading state, and error handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SubscriptionBadge } from "@/components/settings/SubscriptionBadge";

beforeEach(() => {
  vi.clearAllMocks();
  global.fetch = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SubscriptionBadge — tier labels", () => {
  it.each([
    ["beta", "Beta"],
    ["free", "Free"],
    ["pro", "Pro"],
    ["lifetime", "Lifetime"],
  ])("renders correct label for tier '%s'", (tier, expectedLabel) => {
    render(<SubscriptionBadge tier={tier} />);
    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });

  it("falls back to raw tier string for unknown tier", () => {
    render(<SubscriptionBadge tier="enterprise" />);
    expect(screen.getByText("enterprise")).toBeInTheDocument();
  });
});

describe("SubscriptionBadge — billing button visibility", () => {
  it("shows 'Manage billing' for pro tier", () => {
    render(<SubscriptionBadge tier="pro" />);
    expect(screen.getByText("Manage billing")).toBeInTheDocument();
  });

  it("shows 'Manage billing' for lifetime tier", () => {
    render(<SubscriptionBadge tier="lifetime" />);
    expect(screen.getByText("Manage billing")).toBeInTheDocument();
  });

  it("does NOT show 'Manage billing' for beta tier", () => {
    render(<SubscriptionBadge tier="beta" />);
    expect(screen.queryByText("Manage billing")).not.toBeInTheDocument();
  });

  it("does NOT show 'Manage billing' for free tier", () => {
    render(<SubscriptionBadge tier="free" />);
    expect(screen.queryByText("Manage billing")).not.toBeInTheDocument();
  });

  it("shows plan details placeholder for non-billing tiers", () => {
    render(<SubscriptionBadge tier="beta" />);
    expect(
      screen.getByText("Your plan details will appear here.")
    ).toBeInTheDocument();
  });
});

describe("SubscriptionBadge — billing flow", () => {
  const user = userEvent.setup();

  it("clicking 'Manage billing' triggers POST and redirects", async () => {
    const mockLocationHref = vi.fn();
    Object.defineProperty(window, "location", {
      value: { href: "" },
      writable: true,
      configurable: true,
    });

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ url: "https://billing.stripe.com/session/test" }),
    });

    render(<SubscriptionBadge tier="pro" />);
    await user.click(screen.getByText("Manage billing"));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/settings/billing-portal",
        { method: "POST" }
      );
    });

    await waitFor(() => {
      expect(window.location.href).toBe(
        "https://billing.stripe.com/session/test"
      );
    });
  });

  it("shows loading state during billing fetch", async () => {
    // Use a promise we control to keep the loading state visible
    let resolvePromise: (value: unknown) => void;
    const pendingPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });

    (global.fetch as ReturnType<typeof vi.fn>).mockReturnValueOnce(pendingPromise);

    render(<SubscriptionBadge tier="pro" />);
    const user2 = userEvent.setup();
    await user2.click(screen.getByText("Manage billing"));

    // Should show loading text
    await waitFor(() => {
      expect(screen.getByText("Opening...")).toBeInTheDocument();
    });

    // Resolve to clean up
    resolvePromise!({
      ok: true,
      json: async () => ({ url: "https://billing.stripe.com/session/x" }),
    });
  });

  it("handles billing API error gracefully", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "No billing account found" }),
    });

    render(<SubscriptionBadge tier="pro" />);
    const user2 = userEvent.setup();
    await user2.click(screen.getByText("Manage billing"));

    await waitFor(() => {
      expect(
        screen.getByText("No billing account found")
      ).toBeInTheDocument();
    });
  });

  it("handles network error gracefully", async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("Network error")
    );

    render(<SubscriptionBadge tier="lifetime" />);
    const user2 = userEvent.setup();
    await user2.click(screen.getByText("Manage billing"));

    await waitFor(() => {
      expect(
        screen.getByText("Could not reach billing service")
      ).toBeInTheDocument();
    });
  });
});
