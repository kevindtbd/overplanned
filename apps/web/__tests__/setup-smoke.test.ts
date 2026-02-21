import { describe, it, expect } from "vitest";

describe("test infrastructure", () => {
  it("vitest runs", () => {
    expect(1 + 1).toBe(2);
  });

  it("jsdom is available", () => {
    const div = document.createElement("div");
    div.textContent = "hello";
    expect(div.textContent).toBe("hello");
  });
});
