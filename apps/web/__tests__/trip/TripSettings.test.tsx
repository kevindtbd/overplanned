/**
 * Component tests for TripSettings — settings panel with edit, export, archive, delete.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TripSettings } from "@/components/trip/TripSettings";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
  })),
}));

// Mock downloadIcsFile
vi.mock("@/lib/ics-export", () => ({
  downloadIcsFile: vi.fn(),
}));

const { useRouter } = await import("next/navigation");
const { downloadIcsFile } = await import("@/lib/ics-export");

const mockRouter = { push: vi.fn() };

function makeTrip(overrides: Record<string, unknown> = {}) {
  return {
    id: "trip-1",
    name: "Tokyo Trip",
    destination: "Tokyo, Japan",
    city: "Tokyo",
    country: "Japan",
    status: "planning",
    mode: "solo",
    startDate: "2026-07-01T00:00:00Z",
    endDate: "2026-07-04T00:00:00Z",
    timezone: "Asia/Tokyo",
    slots: [],
    ...overrides,
  };
}

describe("TripSettings — form rendering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRouter).mockReturnValue(mockRouter as never);
    global.fetch = vi.fn();
  });

  it("renders form with current trip values", () => {
    const trip = makeTrip();
    render(
      <TripSettings
        trip={trip}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    expect(screen.getByLabelText("Trip name")).toHaveValue("Tokyo Trip");
    expect(screen.getByText("Trip Settings")).toBeInTheDocument();
  });

  it("renders export button", () => {
    render(
      <TripSettings
        trip={makeTrip()}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    expect(screen.getByText("Export to Calendar (.ics)")).toBeInTheDocument();
  });
});

describe("TripSettings — save behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRouter).mockReturnValue(mockRouter as never);
  });

  it("save calls PATCH with only changed fields", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onTripUpdate = vi.fn();
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    global.fetch = mockFetch;

    render(
      <TripSettings
        trip={makeTrip()}
        myRole="organizer"
        onClose={onClose}
        onTripUpdate={onTripUpdate}
      />
    );

    const nameInput = screen.getByLabelText("Trip name");
    await user.clear(nameInput);
    await user.type(nameInput, "Renamed Trip");

    await user.click(screen.getByText("Save changes"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith("/api/trips/trip-1", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Renamed Trip" }),
      });
    });

    await waitFor(() => {
      expect(onTripUpdate).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("cancel closes panel without saving", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const mockFetch = vi.fn();
    global.fetch = mockFetch;

    render(
      <TripSettings
        trip={makeTrip()}
        myRole="organizer"
        onClose={onClose}
        onTripUpdate={vi.fn()}
      />
    );

    await user.click(screen.getByText("Cancel"));

    expect(onClose).toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("TripSettings — danger zone visibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRouter).mockReturnValue(mockRouter as never);
    global.fetch = vi.fn();
  });

  it("shows archive button only for completed trips + organizer", () => {
    render(
      <TripSettings
        trip={makeTrip({ status: "completed" })}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    expect(screen.getByText("Archive trip")).toBeInTheDocument();
    expect(screen.queryByText("Delete trip")).not.toBeInTheDocument();
  });

  it("shows delete button only for draft trips + organizer", () => {
    render(
      <TripSettings
        trip={makeTrip({ status: "draft" })}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    expect(screen.getByText("Delete trip")).toBeInTheDocument();
    expect(screen.queryByText("Archive trip")).not.toBeInTheDocument();
  });

  it("hides danger zone for non-organizer", () => {
    render(
      <TripSettings
        trip={makeTrip({ status: "draft" })}
        myRole="member"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    expect(screen.queryByText("Delete trip")).not.toBeInTheDocument();
    expect(screen.queryByText("Archive trip")).not.toBeInTheDocument();
  });

  it("hides danger zone for planning status", () => {
    render(
      <TripSettings
        trip={makeTrip({ status: "planning" })}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    expect(screen.queryByText("Delete trip")).not.toBeInTheDocument();
    expect(screen.queryByText("Archive trip")).not.toBeInTheDocument();
  });

  it("hides danger zone for active status", () => {
    render(
      <TripSettings
        trip={makeTrip({ status: "active" })}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    expect(screen.queryByText("Delete trip")).not.toBeInTheDocument();
    expect(screen.queryByText("Archive trip")).not.toBeInTheDocument();
  });
});

describe("TripSettings — delete confirmation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRouter).mockReturnValue(mockRouter as never);
  });

  it("delete shows confirmation, cancel aborts", async () => {
    const user = userEvent.setup();
    global.fetch = vi.fn();

    render(
      <TripSettings
        trip={makeTrip({ status: "draft" })}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    // Click delete to show confirmation
    await user.click(screen.getByText("Delete trip"));
    expect(screen.getByText("Delete this draft? This cannot be undone.")).toBeInTheDocument();

    // Cancel the confirmation — use getAllByText since both form Cancel and confirmation Cancel exist
    const cancelButtons = screen.getAllByText("Cancel");
    // The confirmation Cancel is the last one rendered (inside the danger zone)
    await user.click(cancelButtons[cancelButtons.length - 1]);
    expect(screen.queryByText("Delete this draft? This cannot be undone.")).not.toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("confirming delete calls DELETE and redirects to dashboard", async () => {
    const user = userEvent.setup();
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ deleted: true }),
    });
    global.fetch = mockFetch;

    render(
      <TripSettings
        trip={makeTrip({ status: "draft" })}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    await user.click(screen.getByText("Delete trip"));
    await user.click(screen.getByText("Yes, delete"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith("/api/trips/trip-1", {
        method: "DELETE",
      });
    });

    await waitFor(() => {
      expect(mockRouter.push).toHaveBeenCalledWith("/dashboard");
    });
  });
});

describe("TripSettings — date validation errors", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRouter).mockReturnValue(mockRouter as never);
  });

  it("shows error when end date is set before start date and save is clicked", async () => {
    const user = userEvent.setup();
    const mockFetch = vi.fn();
    global.fetch = mockFetch;

    render(
      <TripSettings
        trip={makeTrip({
          startDate: "2026-07-01T00:00:00Z",
          endDate: "2026-07-04T00:00:00Z",
        })}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    const endInput = screen.getByLabelText("End date");
    // Set end date before start date
    await user.clear(endInput);
    await user.type(endInput, "2026-06-28");

    await user.click(screen.getByText("Save changes"));

    await waitFor(() => {
      expect(screen.getByText("End date must be after start date")).toBeInTheDocument();
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("shows error when date range exceeds 14 nights and save is clicked", async () => {
    const user = userEvent.setup();
    const mockFetch = vi.fn();
    global.fetch = mockFetch;

    render(
      <TripSettings
        trip={makeTrip({
          startDate: "2026-07-01T00:00:00Z",
          endDate: "2026-07-04T00:00:00Z",
        })}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    const endInput = screen.getByLabelText("End date");
    await user.clear(endInput);
    await user.type(endInput, "2026-07-20");

    await user.click(screen.getByText("Save changes"));

    await waitFor(() => {
      expect(screen.getByText("Trip cannot exceed 14 nights")).toBeInTheDocument();
    });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe("TripSettings — export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRouter).mockReturnValue(mockRouter as never);
    global.fetch = vi.fn();
  });

  it("export button calls downloadIcsFile with trip data", async () => {
    const user = userEvent.setup();
    const trip = makeTrip();

    render(
      <TripSettings
        trip={trip}
        myRole="organizer"
        onClose={vi.fn()}
        onTripUpdate={vi.fn()}
      />
    );

    await user.click(screen.getByText("Export to Calendar (.ics)"));

    expect(vi.mocked(downloadIcsFile)).toHaveBeenCalledTimes(1);
    const callArg = vi.mocked(downloadIcsFile).mock.calls[0][0];
    expect(callArg.id).toBe("trip-1");
    expect(callArg.destination).toBe("Tokyo, Japan");
    expect(callArg.timezone).toBe("Asia/Tokyo");
  });
});
