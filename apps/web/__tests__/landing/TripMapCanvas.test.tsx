import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import TripMapCanvas from "@/components/landing/TripMapCanvas";

const mockCtx = {
  setTransform: vi.fn(),
  scale: vi.fn(),
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  stroke: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  fillRect: vi.fn(),
  fillText: vi.fn(),
  setLineDash: vi.fn(),
  createRadialGradient: vi.fn(() => ({
    addColorStop: vi.fn(),
  })),
  fillStyle: "",
  strokeStyle: "",
  lineWidth: 1,
  globalAlpha: 1,
  font: "",
  textAlign: "",
};

beforeEach(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (HTMLCanvasElement.prototype as any).getContext = vi.fn(() => mockCtx as unknown as CanvasRenderingContext2D);

  vi.stubGlobal("IntersectionObserver", class {
    observe = vi.fn();
    disconnect = vi.fn();
    unobserve = vi.fn();
    root = null;
    rootMargin = "";
    thresholds = [] as number[];
    takeRecords = () => [] as IntersectionObserverEntry[];
    constructor(_cb: IntersectionObserverCallback, _opts?: IntersectionObserverInit) {}
  });

  Object.defineProperty(document, "fonts", {
    value: { ready: Promise.resolve() },
    configurable: true,
  });

  // Mock getComputedStyle + matchMedia
  vi.stubGlobal("getComputedStyle", vi.fn(() => ({
    getPropertyValue: () => "#EAE4DA",
  })));
  vi.stubGlobal("matchMedia", vi.fn(() => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })));
});

describe("TripMapCanvas", () => {
  it("renders a canvas element", () => {
    const { container } = render(<TripMapCanvas />);
    expect(container.querySelector("canvas")).toBeInstanceOf(HTMLCanvasElement);
  });

  it("acquires 2d context on mount", () => {
    render(<TripMapCanvas />);
    expect(HTMLCanvasElement.prototype.getContext).toHaveBeenCalledWith("2d");
  });

  it("sets aria-hidden on wrapper", () => {
    const { container } = render(<TripMapCanvas />);
    const wrapper = container.firstElementChild;
    expect(wrapper?.getAttribute("aria-hidden")).toBe("true");
  });

  it("cleans up rAF and observer on unmount", () => {
    const cancelSpy = vi.spyOn(window, "cancelAnimationFrame");
    const { unmount } = render(<TripMapCanvas />);
    unmount();
    expect(cancelSpy).toHaveBeenCalled();
    cancelSpy.mockRestore();
  });

  it("cleans up resize listener on unmount", () => {
    const removeSpy = vi.spyOn(window, "removeEventListener");
    const { unmount } = render(<TripMapCanvas />);
    unmount();
    const calls = removeSpy.mock.calls.map((c) => c[0]);
    expect(calls).toContain("resize");
    removeSpy.mockRestore();
  });
});
