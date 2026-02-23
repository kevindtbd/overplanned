import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

vi.mock("@dnd-kit/core", () => ({
  DndContext: ({ children }: any) => <div>{children}</div>,
  closestCenter: vi.fn(),
  KeyboardSensor: vi.fn(),
  PointerSensor: vi.fn(),
  useSensor: vi.fn(),
  useSensors: vi.fn().mockReturnValue([]),
}));

vi.mock("@dnd-kit/sortable", () => ({
  SortableContext: ({ children }: any) => <div>{children}</div>,
  sortableKeyboardCoordinates: vi.fn(),
  verticalListSortingStrategy: vi.fn(),
  useSortable: () => ({
    attributes: {},
    listeners: {},
    setNodeRef: vi.fn(),
    transform: null,
    transition: null,
    isDragging: false,
  }),
}));

vi.mock("@dnd-kit/utilities", () => ({
  CSS: { Transform: { toString: () => null } },
}));

vi.mock("@/components/trip/CityCombobox", () => ({
  CityCombobox: ({ value, onChange, id }: any) => (
    <input
      data-testid={id || "city-combobox"}
      value={value?.city || ""}
      onChange={(e) =>
        onChange({
          city: e.target.value,
          country: "TestCountry",
          timezone: "UTC",
          destination: `${e.target.value}, TestCountry`,
        })
      }
    />
  ),
}));

const mockFetch = vi.fn();
global.fetch = mockFetch;

import { LegEditor } from "@/components/trip/LegEditor";
import type { LegRowData } from "@/components/trip/LegEditorRow";

const TRIP_ID = "11111111-1111-1111-1111-111111111111";

function makeTestLegs(): LegRowData[] {
  return [
    {
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      city: "Tokyo",
      country: "Japan",
      timezone: "Asia/Tokyo",
      destination: "Tokyo, Japan",
      startDate: "2026-04-01T00:00:00.000Z",
      endDate: "2026-04-05T00:00:00.000Z",
      position: 0,
    },
    {
      id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      city: "Kyoto",
      country: "Japan",
      timezone: "Asia/Tokyo",
      destination: "Kyoto, Japan",
      startDate: "2026-04-05T00:00:00.000Z",
      endDate: "2026-04-08T00:00:00.000Z",
      position: 1,
    },
  ];
}

describe("LegEditor", () => {
  let onLegsChange: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetAllMocks();
    onLegsChange = vi.fn();
  });

  function renderEditor(overrides: Partial<Parameters<typeof LegEditor>[0]> = {}) {
    return render(
      <LegEditor
        tripId={TRIP_ID}
        legs={makeTestLegs()}
        tripStatus="planning"
        isOrganizer={true}
        onLegsChange={onLegsChange}
        {...overrides}
      />
    );
  }

  it("renders all legs as rows with city names", () => {
    renderEditor();

    expect(screen.getByTestId("leg-row-0")).toBeInTheDocument();
    expect(screen.getByTestId("leg-row-1")).toBeInTheDocument();
    expect(screen.getByText("Tokyo")).toBeInTheDocument();
    expect(screen.getByText("Kyoto")).toBeInTheDocument();
  });

  it("shows 'Cities (2/8)' count label", () => {
    renderEditor();

    expect(screen.getByText("Cities (2/8)")).toBeInTheDocument();
  });

  it("shows 'Add city' button for organizer on draft/planning trips", () => {
    renderEditor({ tripStatus: "draft", isOrganizer: true });

    expect(screen.getByTestId("add-leg-button")).toBeInTheDocument();
  });

  it("hides 'Add city' button when not organizer", () => {
    renderEditor({ isOrganizer: false });

    expect(screen.queryByTestId("add-leg-button")).not.toBeInTheDocument();
  });

  it("hides 'Add city' button when trip is active status", () => {
    renderEditor({ tripStatus: "active" });

    expect(screen.queryByTestId("add-leg-button")).not.toBeInTheDocument();
  });

  it("move down button calls reorder API with swapped positions", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ reordered: true }),
    });

    renderEditor();

    fireEvent.click(screen.getByTestId("leg-move-down-0"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/trips/${TRIP_ID}/legs/reorder`,
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            legOrder: [
              "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
              "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ],
          }),
        })
      );
    });

    await waitFor(() => {
      expect(onLegsChange).toHaveBeenCalled();
    });
  });

  it("move up button calls reorder API with swapped positions", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ reordered: true }),
    });

    renderEditor();

    fireEvent.click(screen.getByTestId("leg-move-up-1"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/trips/${TRIP_ID}/legs/reorder`,
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            legOrder: [
              "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
              "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ],
          }),
        })
      );
    });

    await waitFor(() => {
      expect(onLegsChange).toHaveBeenCalled();
    });
  });

  it("'Add city' button shows inline add form", () => {
    renderEditor();

    fireEvent.click(screen.getByTestId("add-leg-button"));

    // The add form should now be visible with date inputs and cancel button
    expect(screen.getByLabelText("Start")).toBeInTheDocument();
    expect(screen.getByLabelText("End")).toBeInTheDocument();
    // The "Add city" button in the toolbar should be gone (replaced by form)
    expect(screen.queryByTestId("add-leg-button")).not.toBeInTheDocument();
  });

  it("submitting add form calls POST /api/trips/{id}/legs and onLegsChange", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ id: "cccccccc-cccc-cccc-cccc-cccccccccccc" }),
    });

    renderEditor();

    // Open the add form
    fireEvent.click(screen.getByTestId("add-leg-button"));

    // Fill in the city via the mocked CityCombobox
    fireEvent.change(screen.getByTestId("add-leg-city"), {
      target: { value: "Osaka" },
    });

    // Fill in dates
    fireEvent.change(screen.getByLabelText("Start"), {
      target: { value: "2026-04-09" },
    });
    fireEvent.change(screen.getByLabelText("End"), {
      target: { value: "2026-04-12" },
    });

    // Click the submit "Add city" button inside the form
    const addButtons = screen.getAllByText("Add city");
    const submitButton = addButtons.find(
      (btn) => btn.tagName === "BUTTON" && !btn.closest("[data-testid='add-leg-button']")
    )!;
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/trips/${TRIP_ID}/legs`,
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/json" },
        })
      );
    });

    await waitFor(() => {
      expect(onLegsChange).toHaveBeenCalled();
    });
  });

  it("remove button shows confirm, confirming calls DELETE and onLegsChange", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ deleted: true }),
    });

    renderEditor();

    // Click trash on the second leg (index 1)
    fireEvent.click(screen.getByTestId("leg-remove-1"));

    // Confirm dialog should appear with "Remove" and "No" options
    expect(screen.getByText("Remove")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();

    // Click "Remove" to confirm
    fireEvent.click(screen.getByText("Remove"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/trips/${TRIP_ID}/legs/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb`,
        expect.objectContaining({ method: "DELETE" })
      );
    });

    await waitFor(() => {
      expect(onLegsChange).toHaveBeenCalled();
    });
  });
});
