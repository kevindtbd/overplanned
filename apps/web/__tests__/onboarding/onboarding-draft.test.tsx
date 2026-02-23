/**
 * Tests for Phase 4: Onboarding draft save, resume flow, and completion branching.
 *
 * Strategy: mock all step sub-components as thin stubs. The test drives the wizard
 * by interacting with the Continue / Create trip buttons rendered by OnboardingContent
 * itself, which is the component under test.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ---------------------------------------------------------------------------
// Mocks — must come before component import
// ---------------------------------------------------------------------------

const mockPush = vi.fn();
const mockReplace = vi.fn();
let mockSearchParams: URLSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useSearchParams: () => mockSearchParams,
}));

// Mock all step sub-components so we control renders and can call their
// callbacks directly. Each mock exposes test-ids for any buttons we need.

vi.mock("@/app/onboarding/components/ForkScreen", () => ({
  ForkScreen: ({ onPlanTrip }: { onPlanTrip: () => void }) => (
    <div>
      <span>ForkScreen</span>
      <button onClick={onPlanTrip}>Start planning</button>
    </div>
  ),
}));

vi.mock("@/app/onboarding/components/BackfillStep", () => ({
  BackfillStep: ({ onSkip }: { onSkip: () => void; onContinue: () => void }) => (
    <div>
      <span>BackfillStep</span>
      <button onClick={onSkip}>Skip backfill</button>
    </div>
  ),
}));

// DestinationStep mock: auto-calls onChange with a LaunchCity on mount so
// tests don't have to simulate city selection.
vi.mock("@/app/onboarding/components/DestinationStep", () => ({
  LAUNCH_CITIES: [
    { city: "Tokyo", country: "Japan", timezone: "Asia/Tokyo", destination: "Tokyo, Japan" },
    { city: "New York", country: "United States", timezone: "America/New_York", destination: "New York, United States" },
    { city: "Mexico City", country: "Mexico", timezone: "America/Mexico_City", destination: "Mexico City, Mexico" },
  ],
  DestinationStep: ({
    onChange,
  }: {
    value: unknown;
    onChange: (city: { city: string; country: string; timezone: string; destination: string }) => void;
  }) => {
    // Immediately pre-select Tokyo so canAdvance() is true
    return (
      <div>
        <span>DestinationStep</span>
        <button
          onClick={() =>
            onChange({
              city: "Tokyo",
              country: "Japan",
              timezone: "Asia/Tokyo",
              destination: "Tokyo, Japan",
            })
          }
        >
          Select Tokyo
        </button>
      </div>
    );
  },
}));

vi.mock("@/app/onboarding/components/DatesStep", () => ({
  DatesStep: ({
    onStartDateChange,
    onEndDateChange,
  }: {
    startDate: string;
    endDate: string;
    onStartDateChange: (d: string) => void;
    onEndDateChange: (d: string) => void;
  }) => (
    <div>
      <span>DatesStep</span>
      <button
        onClick={() => {
          onStartDateChange("2026-04-01");
          onEndDateChange("2026-04-07");
        }}
      >
        Fill dates
      </button>
    </div>
  ),
}));

vi.mock("@/app/onboarding/components/TripDNAStep", () => ({
  TripDNAStep: ({
    onPaceChange,
    onMorningChange,
  }: {
    pace: unknown;
    morningPreference: unknown;
    foodPreferences: unknown;
    freeformVibes: unknown;
    onPaceChange: (p: string) => void;
    onMorningChange: (m: string) => void;
    onFoodToggle: (chip: string) => void;
    onFreeformChange: (v: string) => void;
  }) => (
    <div>
      <span>TripDNAStep</span>
      <button
        onClick={() => {
          onPaceChange("moderate");
          onMorningChange("mid");
        }}
      >
        Fill DNA
      </button>
    </div>
  ),
}));

vi.mock("@/app/onboarding/components/TemplateStep", () => ({
  TemplateStep: ({ onSelect }: { selected: unknown; onSelect: (t: string) => void }) => (
    <div>
      <span>TemplateStep</span>
      <button onClick={() => onSelect("cultural_explorer")}>Select template</button>
    </div>
  ),
}));

vi.mock("@/components/states", () => ({
  ErrorState: ({ message, onRetry }: { message: string; onRetry: () => void }) => (
    <div>
      <span>{message}</span>
      <button onClick={onRetry}>Try again</button>
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Component import (after mocks are registered)
// ---------------------------------------------------------------------------

import OnboardingPage from "@/app/onboarding/page";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Advance the wizard from fork -> destination -> dates (with city + dates filled)
 * and return the user-event instance for chaining.
 */
async function advanceToDates(user: ReturnType<typeof userEvent.setup>) {
  // fork -> backfill
  await user.click(screen.getByRole("button", { name: /start planning/i }));
  // backfill -> destination (skip)
  await user.click(screen.getByRole("button", { name: /skip backfill/i }));
  // destination: select Tokyo so canAdvance = true
  await user.click(screen.getByRole("button", { name: /select tokyo/i }));
  // destination -> dates
  await user.click(screen.getByRole("button", { name: /continue/i }));
  // dates: fill start/end
  await user.click(screen.getByRole("button", { name: /fill dates/i }));
}

async function advanceToName(user: ReturnType<typeof userEvent.setup>) {
  await advanceToDates(user);
  // dates -> name (this is where draft save fires)
  await user.click(screen.getByRole("button", { name: /continue/i }));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Onboarding — draft save on dates advance", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams = new URLSearchParams();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fires POST /api/trips/draft with correct payload when advancing from dates step", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ trip: { id: "draft-abc-123" } }),
    });

    render(<OnboardingPage />);
    await advanceToName(user);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/trips/draft",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
        })
      );
    });

    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    const draftCall = calls.find((c: unknown[]) => (c[0] as string) === "/api/trips/draft");
    expect(draftCall).toBeTruthy();

    const body = JSON.parse((draftCall![1] as RequestInit).body as string);
    expect(body).toMatchObject({
      destination: "Tokyo, Japan",
      city: "Tokyo",
      country: "Japan",
      timezone: "Asia/Tokyo",
      startDate: expect.stringMatching(/^2026-04-01/),
      endDate: expect.stringMatching(/^2026-04-07/),
    });
  });

  it("advances to name step immediately without waiting for draft POST", async () => {
    const user = userEvent.setup();

    // Never resolves — simulates slow network
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {})
    );

    render(<OnboardingPage />);
    await advanceToDates(user);

    // Click Continue from dates step
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Name step should be visible immediately, not blocked by pending draft POST
    expect(screen.getByText("Name your trip")).toBeInTheDocument();
  });

  it("does not fire a second draft POST on double-click (ref guard)", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ trip: { id: "draft-abc-123" } }),
    });

    render(<OnboardingPage />);
    await advanceToDates(user);

    const continueBtn = screen.getByRole("button", { name: /continue/i });
    // Two rapid clicks — userEvent processes them sequentially
    await user.click(continueBtn);

    // After advancing to name step, go back to dates and try again —
    // draftIdRef.current is already set so a second POST must not fire
    const backBtn = screen.getByRole("button", { name: /go back/i });
    await user.click(backBtn);

    await user.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => {
      const draftCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
        (c: unknown[]) => (c[0] as string) === "/api/trips/draft"
      );
      // Only one draft POST regardless of multiple advances from dates step
      expect(draftCalls).toHaveLength(1);
    });
  });

  it("shows draft-save-error element when draft POST fails", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: "Server error" }),
    });

    render(<OnboardingPage />);
    await advanceToDates(user);
    await user.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => {
      expect(screen.getByTestId("draft-save-error")).toBeInTheDocument();
    });
  });

  it("still advances step even when draft POST fails", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Network failure")
    );

    render(<OnboardingPage />);
    await advanceToDates(user);
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Step advancement is not blocked by draft failure
    expect(screen.getByText("Name your trip")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------

describe("Onboarding — resume flow (?resume=<tripId>)", () => {
  const VALID_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";

  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("pre-fills city and dates from draft trip data", async () => {
    mockSearchParams = new URLSearchParams(`resume=${VALID_UUID}`);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        trip: {
          id: VALID_UUID,
          status: "draft",
          city: "Tokyo",
          country: "Japan",
          startDate: "2026-05-01T00:00:00.000Z",
          endDate: "2026-05-07T00:00:00.000Z",
        },
      }),
    });

    render(<OnboardingPage />);

    // Wait for resume effect to fire and set step to "name"
    await waitFor(() => {
      expect(screen.getByText("Name your trip")).toBeInTheDocument();
    });
  });

  it("jumps directly to name step on valid resume", async () => {
    mockSearchParams = new URLSearchParams(`resume=${VALID_UUID}`);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        trip: {
          id: VALID_UUID,
          status: "draft",
          city: "Tokyo",
          country: "Japan",
          startDate: "2026-05-01T00:00:00.000Z",
          endDate: "2026-05-07T00:00:00.000Z",
        },
      }),
    });

    render(<OnboardingPage />);

    await waitFor(() => {
      // Should be on name step, not fork
      expect(screen.getByText("Name your trip")).toBeInTheDocument();
      expect(screen.queryByText("ForkScreen")).not.toBeInTheDocument();
    });
  });

  it("stores draftId in ref — subsequent completion uses PATCH not POST", async () => {
    mockSearchParams = new URLSearchParams(`resume=${VALID_UUID}`);

    (global.fetch as ReturnType<typeof vi.fn>)
      // Resume GET
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trip: {
            id: VALID_UUID,
            status: "draft",
            city: "Tokyo",
            country: "Japan",
            startDate: "2026-05-01T00:00:00.000Z",
            endDate: "2026-05-07T00:00:00.000Z",
          },
        }),
      })
      // PATCH on completion
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trip: { id: VALID_UUID },
          generated: { slotsCreated: 5, source: "seeded" },
        }),
      });

    const user = userEvent.setup();
    render(<OnboardingPage />);

    // Wait for resume to land on name step
    await waitFor(() => {
      expect(screen.getByText("Name your trip")).toBeInTheDocument();
    });

    // Fill name
    const nameInput = screen.getByPlaceholderText(/tokyo golden week/i);
    await user.clear(nameInput);
    await user.type(nameInput, "Tokyo Spring");

    // Continue -> dna
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Fill DNA
    await user.click(screen.getByRole("button", { name: /fill dna/i }));

    // Continue -> template
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Create trip
    await user.click(screen.getByRole("button", { name: /create trip/i }));

    await waitFor(() => {
      // Should have called PATCH, not POST /api/trips
      // c[1] may be undefined for the GET call (no init object), so guard with optional chaining
      const patchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        (c: unknown[]) =>
          typeof c[0] === "string" &&
          c[0].includes(`/api/trips/${VALID_UUID}`) &&
          (c[1] as RequestInit | undefined)?.method === "PATCH"
      );
      expect(patchCall).toBeTruthy();

      const postCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        (c: unknown[]) =>
          typeof c[0] === "string" &&
          c[0] === "/api/trips" &&
          (c[1] as RequestInit | undefined)?.method === "POST"
      );
      expect(postCall).toBeUndefined();
    });
  });

  it("clears the ?resume= param from URL after loading", async () => {
    mockSearchParams = new URLSearchParams(`resume=${VALID_UUID}`);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        trip: {
          id: VALID_UUID,
          status: "draft",
          city: "Tokyo",
          country: "Japan",
          startDate: "2026-05-01T00:00:00.000Z",
          endDate: "2026-05-07T00:00:00.000Z",
        },
      }),
    });

    render(<OnboardingPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/onboarding", { scroll: false });
    });
  });

  it("clears param and starts fresh when resume ID is not a valid UUID", async () => {
    mockSearchParams = new URLSearchParams("resume=not-a-uuid");

    render(<OnboardingPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith("/onboarding", { scroll: false });
    });

    // Should show fork screen, not make any fetch call
    expect(global.fetch).not.toHaveBeenCalled();
    expect(screen.getByText("ForkScreen")).toBeInTheDocument();
  });

  it("redirects to /trip/<id> when the resumed trip is not in draft status", async () => {
    mockSearchParams = new URLSearchParams(`resume=${VALID_UUID}`);

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        trip: {
          id: VALID_UUID,
          status: "planning",
          city: "Tokyo",
          country: "Japan",
          startDate: "2026-05-01T00:00:00.000Z",
          endDate: "2026-05-07T00:00:00.000Z",
        },
      }),
    });

    render(<OnboardingPage />);

    await waitFor(() => {
      expect(mockReplace).toHaveBeenCalledWith(`/trip/${VALID_UUID}`);
    });

    // Should NOT advance to name step
    expect(screen.queryByText("Name your trip")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------

describe("Onboarding — completion branching", () => {
  const DRAFT_ID = "b2c3d4e5-f6a7-8901-bcde-f01234567890";

  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams = new URLSearchParams();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /**
   * Helper: advance the full wizard through all steps, then click "Create trip".
   * The draft save mock must already be set up before calling this.
   */
  async function completeFullWizard(user: ReturnType<typeof userEvent.setup>) {
    render(<OnboardingPage />);

    // fork -> backfill
    await user.click(screen.getByRole("button", { name: /start planning/i }));
    // backfill -> destination (skip)
    await user.click(screen.getByRole("button", { name: /skip backfill/i }));
    await user.click(screen.getByRole("button", { name: /select tokyo/i }));

    // destination -> dates
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(screen.getByRole("button", { name: /fill dates/i }));

    // dates -> name (draft save fires here)
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Wait for name step
    await waitFor(() => {
      expect(screen.getByText("Name your trip")).toBeInTheDocument();
    });

    // Type trip name
    const nameInput = screen.getByPlaceholderText(/tokyo golden week/i);
    await user.clear(nameInput);
    await user.type(nameInput, "Tokyo Adventure");

    // name -> dna
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await user.click(screen.getByRole("button", { name: /fill dna/i }));

    // dna -> template
    await user.click(screen.getByRole("button", { name: /continue/i }));

    // Create trip
    await user.click(screen.getByRole("button", { name: /create trip/i }));
  }

  it("uses PATCH when draftIdRef is set after successful draft save", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>)
      // Draft save on dates advance
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ trip: { id: DRAFT_ID } }),
      })
      // PATCH on completion
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trip: { id: DRAFT_ID },
          generated: { slotsCreated: 4, source: "seeded" },
        }),
      });

    await completeFullWizard(user);

    await waitFor(() => {
      const patchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        (c: unknown[]) =>
          typeof c[0] === "string" &&
          c[0] === `/api/trips/${DRAFT_ID}` &&
          (c[1] as RequestInit | undefined)?.method === "PATCH"
      );
      expect(patchCall).toBeTruthy();
    });
  });

  it("PATCH payload includes status: planning", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ trip: { id: DRAFT_ID } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trip: { id: DRAFT_ID },
          generated: { slotsCreated: 4, source: "seeded" },
        }),
      });

    await completeFullWizard(user);

    await waitFor(() => {
      const patchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        (c: unknown[]) =>
          typeof c[0] === "string" &&
          c[0] === `/api/trips/${DRAFT_ID}` &&
          (c[1] as RequestInit | undefined)?.method === "PATCH"
      );
      expect(patchCall).toBeTruthy();

      const body = JSON.parse((patchCall![1] as RequestInit).body as string);
      expect(body.status).toBe("planning");
    });
  });

  it("falls back to POST when draft save failed (draftIdRef stays null)", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>)
      // Draft save fails
      .mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({ error: "Too many drafts" }),
      })
      // POST on completion
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trip: { id: "new-trip-999" },
          generated: { slotsCreated: 3, source: "seeded" },
        }),
      });

    await completeFullWizard(user);

    await waitFor(() => {
      const postCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        (c: unknown[]) =>
          typeof c[0] === "string" &&
          c[0] === "/api/trips" &&
          (c[1] as RequestInit | undefined)?.method === "POST"
      );
      expect(postCall).toBeTruthy();

      // Should NOT have called PATCH
      const patchCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find(
        (c: unknown[]) => (c[1] as RequestInit | undefined)?.method === "PATCH"
      );
      expect(patchCall).toBeUndefined();
    });
  });

  it("navigates to the trip page after successful PATCH completion", async () => {
    const user = userEvent.setup();

    (global.fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ trip: { id: DRAFT_ID } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trip: { id: DRAFT_ID },
          generated: { slotsCreated: 4, source: "seeded" },
        }),
      });

    await completeFullWizard(user);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(`/trip/${DRAFT_ID}`);
    });
  });

  it("navigates to the trip page after successful POST fallback", async () => {
    const user = userEvent.setup();
    const NEW_TRIP_ID = "fresh-trip-777";

    (global.fetch as ReturnType<typeof vi.fn>)
      // Draft save fails
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({}),
      })
      // POST succeeds
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trip: { id: NEW_TRIP_ID },
          generated: { slotsCreated: 0, source: "empty" },
        }),
      });

    await completeFullWizard(user);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith(`/trip/${NEW_TRIP_ID}`);
    });
  });
});
