import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

// Suppress console.error and console.warn during tests to prevent stderr
// flooding in CI. Messages are silently captured — if you need to assert on
// them, use vi.spyOn(console, "error") in the individual test.
const originalError = console.error;
const originalWarn = console.warn;

afterEach(() => {
  // Restore in case a test replaced them with its own spy
  console.error = originalError;
  console.warn = originalWarn;
});

// Replace with no-op spies — tests that need to assert on console output
// can still vi.spyOn(console, "error") and it will layer on top.
console.error = vi.fn();
console.warn = vi.fn();
