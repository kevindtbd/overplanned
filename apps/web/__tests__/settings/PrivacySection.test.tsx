import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PrivacySection } from "@/components/settings/PrivacySection";

const mockSignOut = vi.fn();

vi.mock("next-auth/react", () => ({
  signOut: (...args: unknown[]) => mockSignOut(...args),
}));

const CONSENT_DEFAULTS = {
  modelTraining: false,
  anonymizedResearch: false,
};

function mockFetchSuccess(getData = CONSENT_DEFAULTS) {
  const fetchMock = vi.fn();
  // First call = GET (consent)
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => getData,
  });
  // Subsequent calls = PATCH / export / delete
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({}),
  });
  global.fetch = fetchMock;
  return fetchMock;
}

describe("PrivacySection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock URL.createObjectURL and revokeObjectURL
    global.URL.createObjectURL = vi.fn(() => "blob:test");
    global.URL.revokeObjectURL = vi.fn();
  });

  it("renders skeleton during load, then toggles after GET resolves", async () => {
    mockFetchSuccess();
    const { container } = render(<PrivacySection email="test@example.com" />);

    // Skeleton visible
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();

    // After load, toggles appear
    await waitFor(() => {
      expect(container.querySelector(".animate-pulse")).not.toBeInTheDocument();
    });

    const toggles = screen.getAllByRole("switch");
    expect(toggles).toHaveLength(2);
  });

  it("toggle triggers PATCH and reverts on failure", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    // GET succeeds
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => CONSENT_DEFAULTS,
    });
    // PATCH fails
    fetchMock.mockResolvedValueOnce({ ok: false });
    global.fetch = fetchMock;

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getAllByRole("switch")).toHaveLength(2);
    });

    const toggles = screen.getAllByRole("switch");
    // modelTraining starts false
    expect(toggles[0]).toHaveAttribute("aria-checked", "false");

    await user.click(toggles[0]);

    // After PATCH failure, should revert back to false
    await waitFor(() => {
      expect(toggles[0]).toHaveAttribute("aria-checked", "false");
    });
  });

  it("export button triggers blob download", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for export call (will be the 2nd call after GET)
    fetchMock.mockResolvedValueOnce({
      ok: true,
      blob: async () => new Blob(["{}"], { type: "application/json" }),
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Download my data")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Download my data"));

    await waitFor(() => {
      expect(global.URL.createObjectURL).toHaveBeenCalled();
    });
  });

  it("export 429 shows rate limit message", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for export 429
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 429,
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Download my data")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Download my data"));

    await waitFor(() => {
      expect(screen.getByText("Please wait before requesting another export.")).toBeInTheDocument();
    });
  });

  it("export error shows error message", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for export 500
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Download my data")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Download my data"));

    await waitFor(() => {
      expect(screen.getByText("Failed to download. Please try again.")).toBeInTheDocument();
    });
  });

  it("delete shows inline confirmation with email input", async () => {
    const user = userEvent.setup();
    mockFetchSuccess();

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));

    expect(screen.getByText("Type your email to confirm:")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();
    expect(screen.getByText("Yes, delete my account")).toBeInTheDocument();
  });

  it("cancel hides confirmation", async () => {
    const user = userEvent.setup();
    mockFetchSuccess();

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));
    expect(screen.getByText("Type your email to confirm:")).toBeInTheDocument();

    await user.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Type your email to confirm:")).not.toBeInTheDocument();
  });

  it("confirm button disabled until email matches", async () => {
    const user = userEvent.setup();
    mockFetchSuccess();

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));

    const confirmBtn = screen.getByText("Yes, delete my account");
    expect(confirmBtn).toBeDisabled();

    const input = screen.getByPlaceholderText("your@email.com");
    await user.type(input, "test@example.com");

    expect(confirmBtn).not.toBeDisabled();
  });

  it("confirm triggers DELETE + signOut", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for delete success (will be 2nd call after GET)
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ deleted: true }),
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));

    const input = screen.getByPlaceholderText("your@email.com");
    await user.type(input, "test@example.com");
    await user.click(screen.getByText("Yes, delete my account"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/settings/account",
        expect.objectContaining({
          method: "DELETE",
          body: JSON.stringify({ confirmEmail: "test@example.com" }),
        })
      );
      expect(mockSignOut).toHaveBeenCalledWith({ callbackUrl: "/" });
    });
  });

  it("delete failure shows error and resets state", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSuccess();

    // Override for delete failure
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    render(<PrivacySection email="test@example.com" />);

    await waitFor(() => {
      expect(screen.getByText("Delete my account")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Delete my account"));

    const input = screen.getByPlaceholderText("your@email.com");
    await user.type(input, "test@example.com");
    await user.click(screen.getByText("Yes, delete my account"));

    await waitFor(() => {
      expect(screen.getByText("Failed to delete account. Please try again.")).toBeInTheDocument();
    });

    // Confirm button should be re-enabled (not stuck in deleting state)
    expect(screen.getByText("Yes, delete my account")).not.toBeDisabled();
  });
});
