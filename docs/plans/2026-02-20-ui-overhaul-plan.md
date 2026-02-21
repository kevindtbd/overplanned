# UI Visual Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the scaffolded UI into a pixel-accurate implementation of the 22 HTML mockups with real backend data, full design token system, and light/dark theme support.

**Architecture:** Bottom-up sequential build. Phase 0 (test infra) -> Phase 1 (tokens + theme + fonts) -> Phase 2 (components + token migration) -> Phase 3+4 (API routes interleaved with screens). Each phase is one atomic commit. Phase 1 keeps backward-compatible aliases so the app doesn't break before Phase 2.

**Tech Stack:** Next.js 14 App Router, TypeScript, Tailwind CSS, Prisma ORM, Vitest + @testing-library/react, Playwright, Zod, next/font/google

**Design Doc:** `docs/plans/2026-02-20-ui-overhaul-design.md`

**Critical Context:**
- Ink scale is INVERTED: ink-100 = darkest (primary text), ink-900 = lightest (near-bg)
- Accent color: #C4694F (CLAUDE.md canonical)
- 3 fonts: Sora (body/UI/CTAs/wordmark), DM Mono (data/labels), Lora (serif headlines)
- 50 files use old token class names -- Phase 2 migrates them all
- `@/` path alias = `apps/web/` root

---

## Phase 0: Test Infrastructure

### Task 0.1: Install Test Dependencies

**Files:**
- Modify: `apps/web/package.json`

**Step 1: Install vitest + testing-library + accessibility deps**

Run:
```bash
cd /home/pogchamp/Desktop/overplanned && npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event vitest-mock-extended @vitest/coverage-v8 --workspace=apps/web
```

**Step 2: Install Playwright + axe-core**

Run:
```bash
cd /home/pogchamp/Desktop/overplanned && npm install -D @playwright/test axe-core @axe-core/playwright --workspace=apps/web
```

**Step 3: Install Playwright browsers**

Run:
```bash
npx playwright install chromium
```

---

### Task 0.2: Create Vitest Config

**Files:**
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/vitest.setup.ts`
- Delete: `apps/web/jest.config.ts`

**Step 1: Create vitest.config.ts**

```typescript
// apps/web/vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["__tests__/**/*.test.{ts,tsx}"],
    exclude: ["__tests__/e2e/**"],
    globals: true,
    coverage: {
      provider: "v8",
      include: ["app/**", "lib/**", "components/**"],
      exclude: ["**/*.d.ts", "app/**/layout.tsx"],
    },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./") },
  },
});
```

**Step 2: Create vitest.setup.ts**

```typescript
// apps/web/vitest.setup.ts
import "@testing-library/jest-dom/vitest";
```

**Step 3: Delete jest.config.ts**

Run:
```bash
rm /home/pogchamp/Desktop/overplanned/apps/web/jest.config.ts
```

---

### Task 0.3: Add Test Scripts + Update Playwright Config

**Files:**
- Modify: `apps/web/package.json` (scripts section)
- Modify: `playwright.config.ts`

**Step 1: Add test scripts to apps/web/package.json**

Add to `"scripts"`:
```json
"test": "vitest run",
"test:watch": "vitest",
"test:coverage": "vitest run --coverage",
"test:e2e": "playwright test --config=../../playwright.config.ts"
```

**Step 2: Update playwright.config.ts with mobile/tablet viewports**

Replace the `projects` array in `/home/pogchamp/Desktop/overplanned/playwright.config.ts`:

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./apps/web/__tests__/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "html",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["iPhone 13"] } },
    { name: "tablet", use: { ...devices["iPad (gen 7)"] } },
  ],
  webServer: {
    command: "npm run dev --workspace=apps/web",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
  },
});
```

---

### Task 0.4: Create Test Utility Files

**Files:**
- Create: `apps/web/__tests__/__mocks__/prisma.ts`
- Create: `apps/web/__tests__/__mocks__/auth.ts`
- Create: `apps/web/__tests__/helpers/request.ts`
- Create: `apps/web/__tests__/helpers/render.tsx`

**Step 1: Prisma mock singleton**

```typescript
// apps/web/__tests__/__mocks__/prisma.ts
import { PrismaClient } from "@prisma/client";
import { mockDeep, mockReset, type DeepMockProxy } from "vitest-mock-extended";
import { beforeEach, vi } from "vitest";

export const prismaMock = mockDeep<PrismaClient>();

// Auto-reset between tests
beforeEach(() => {
  mockReset(prismaMock);
});

// Mock the import path used in API routes
vi.mock("@prisma/client", () => ({
  PrismaClient: vi.fn(() => prismaMock),
}));

export type MockPrisma = DeepMockProxy<PrismaClient>;
```

**Step 2: Auth session mock helper**

```typescript
// apps/web/__tests__/__mocks__/auth.ts
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
```

**Step 3: NextRequest factory**

```typescript
// apps/web/__tests__/helpers/request.ts
import { NextRequest } from "next/server";

export function createRequest(
  method: string,
  url: string,
  body?: Record<string, unknown>,
  headers?: Record<string, string>
): NextRequest {
  const init: RequestInit = {
    method,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
  };
  if (body) {
    init.body = JSON.stringify(body);
  }
  return new NextRequest(new URL(url, "http://localhost:3000"), init);
}
```

**Step 4: Custom render wrapper**

```typescript
// apps/web/__tests__/helpers/render.tsx
import { render, type RenderOptions } from "@testing-library/react";
import { type ReactElement } from "react";

function AllProviders({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">
) {
  return render(ui, { wrapper: AllProviders, ...options });
}

export { screen, within, waitFor } from "@testing-library/react";
export { default as userEvent } from "@testing-library/user-event";
```

---

### Task 0.5: Verify Test Infrastructure Works

**Step 1: Write a smoke test**

```typescript
// apps/web/__tests__/setup-smoke.test.ts
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
```

**Step 2: Run it**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/setup-smoke.test.ts`
Expected: 2 tests PASS

**Step 3: Commit Phase 0**

```bash
cd /home/pogchamp/Desktop/overplanned
git add apps/web/vitest.config.ts apps/web/vitest.setup.ts apps/web/package.json apps/web/__tests__/__mocks__/ apps/web/__tests__/helpers/ apps/web/__tests__/setup-smoke.test.ts playwright.config.ts package-lock.json
git commit -m "feat(web): Phase 0 — test infrastructure (vitest + playwright + test utilities)"
```

---

## Phase 1: Token Foundation

### Task 1.1: Rewrite globals.css with Full Token System

**Files:**
- Modify: `apps/web/app/globals.css`

**Step 1: Write the token resolution test**

```typescript
// apps/web/__tests__/tokens/token-resolution.test.ts
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("CSS token resolution", () => {
  const css = fs.readFileSync(
    path.resolve(__dirname, "../../app/globals.css"),
    "utf-8"
  );

  const requiredTokens = [
    "--bg-base", "--bg-surface", "--bg-raised", "--bg-overlay",
    "--bg-input", "--bg-stone", "--bg-warm",
    "--accent", "--accent-light", "--accent-muted", "--accent-fg",
    "--gold", "--gold-light",
    "--ink-100", "--ink-200", "--ink-300", "--ink-400", "--ink-500",
    "--ink-600", "--ink-700", "--ink-800", "--ink-900",
    "--success", "--success-bg", "--info", "--info-bg",
    "--warning", "--warning-bg", "--error", "--error-bg",
    "--shadow-sm", "--shadow-md", "--shadow-lg", "--shadow-card", "--shadow-xl",
    "--transition-fast", "--transition-normal", "--transition-slow",
  ];

  it("defines all required tokens in light theme", () => {
    for (const token of requiredTokens) {
      expect(css).toContain(`${token}:`);
    }
  });

  it("has data-theme light selector", () => {
    expect(css).toContain('[data-theme="light"]');
  });

  it("has data-theme dark selector", () => {
    expect(css).toContain('[data-theme="dark"]');
  });

  it("has prefers-color-scheme dark fallback", () => {
    expect(css).toContain("prefers-color-scheme: dark");
  });

  it("keeps backward-compatible aliases", () => {
    const aliases = [
      "--color-terracotta", "--color-warm-background", "--color-warm-surface",
      "--color-warm-border", "--color-warm-text-primary", "--color-warm-text-secondary",
    ];
    for (const alias of aliases) {
      expect(css).toContain(`${alias}:`);
    }
  });

  it("uses #C4694F for accent (CLAUDE.md canonical)", () => {
    expect(css).toContain("#C4694F");
  });

  it("has shimmer keyframes with reduced-motion pause", () => {
    expect(css).toContain("@keyframes shimmer");
    expect(css).toContain("prefers-reduced-motion");
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/tokens/token-resolution.test.ts`
Expected: FAIL — missing tokens, no data-theme selectors

**Step 3: Rewrite globals.css**

Replace entire contents of `apps/web/app/globals.css` with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* ================================================================
   DESIGN TOKENS — Phase 1
   Source of truth: design-v4.html + CLAUDE.md
   Ink scale: INVERTED — 100=darkest, 900=lightest
   Accent: #C4694F (CLAUDE.md canonical)
   ================================================================ */

[data-theme="light"] {
  /* Background hierarchy */
  --bg-base:      #FAF8F5;
  --bg-surface:   #FFFFFF;
  --bg-raised:    #F3EFE9;
  --bg-overlay:   #EDE8E1;
  --bg-input:     #F3EFE9;
  --bg-stone:     #EAE4DA;
  --bg-warm:      #F5F1EB;

  /* Accent: Terracotta */
  --accent:         #C4694F;
  --accent-light:   #F0E0D9;
  --accent-muted:   #D4886E;
  --accent-fg:      #8C3A24;

  /* Gold */
  --gold:           #A07830;
  --gold-light:     #F5EDD8;

  /* Ink scale (100=darkest primary, 900=lightest near-bg) */
  --ink-100:  #1C1713;
  --ink-200:  #3A302A;
  --ink-300:  #5C5048;
  --ink-400:  #7A6E64;
  --ink-500:  #9C8E84;
  --ink-600:  #BDB0A6;
  --ink-700:  #D6CFC8;
  --ink-800:  #EAE4DE;
  --ink-900:  #F5F1EC;

  /* Semantic */
  --success:     #4A8A5C;
  --success-bg:  #E0EEE5;
  --info:        #3A6A8C;
  --info-bg:     #D8E8F2;
  --warning:     #A07830;
  --warning-bg:  #F2EAD8;
  --error:       #8C2A2A;
  --error-bg:    #F5E0E0;

  /* Shadows (warm-tinted, never blue) */
  --shadow-sm:   0 1px 3px rgba(28,23,19,0.06), 0 1px 2px rgba(28,23,19,0.04);
  --shadow-md:   0 4px 16px rgba(28,23,19,0.08), 0 1px 4px rgba(28,23,19,0.04);
  --shadow-lg:   0 12px 48px rgba(28,23,19,0.10), 0 2px 8px rgba(28,23,19,0.05);
  --shadow-card: 0 2px 8px rgba(28,23,19,0.06);
  --shadow-xl:   0 32px 80px rgba(28,23,19,0.12), 0 8px 24px rgba(28,23,19,0.07);

  /* Transitions */
  --transition-fast:   150ms ease;
  --transition-normal: 200ms ease;
  --transition-slow:   300ms ease-out;

  /* Backward-compatible aliases (REMOVE IN PHASE 2) */
  --color-terracotta:          var(--accent);
  --color-warm-background:     var(--bg-base);
  --color-warm-surface:        var(--bg-surface);
  --color-warm-border:         var(--ink-700);
  --color-warm-text-primary:   var(--ink-100);
  --color-warm-text-secondary: var(--ink-400);
}

[data-theme="dark"] {
  --bg-base:      #100E0B;
  --bg-surface:   #171310;
  --bg-raised:    #1F1A15;
  --bg-overlay:   #28211A;
  --bg-input:     #1F1A15;
  --bg-stone:     #1C1813;
  --bg-warm:      #141109;

  --accent:         #D07050;
  --accent-light:   rgba(208,112,80,0.14);
  --accent-muted:   #8C402A;
  --accent-fg:      #E8906E;

  --gold:           #C8A96E;
  --gold-light:     rgba(200,169,110,0.12);

  --ink-100:  #F0EAE2;
  --ink-200:  #D4C8BC;
  --ink-300:  #A89484;
  --ink-400:  #7A6A5C;
  --ink-500:  #5C4E42;
  --ink-600:  #3D332A;
  --ink-700:  #2E251E;
  --ink-800:  #221C16;
  --ink-900:  #1A1410;

  --success:     #5A9E6A;
  --success-bg:  rgba(90,158,106,0.12);
  --info:        #4A84A8;
  --info-bg:     rgba(74,132,168,0.12);
  --warning:     #B8943A;
  --warning-bg:  rgba(184,148,58,0.12);
  --error:       #C25555;
  --error-bg:    rgba(194,85,85,0.12);

  --shadow-sm:   0 1px 3px rgba(0,0,0,0.3);
  --shadow-md:   0 4px 20px rgba(0,0,0,0.4);
  --shadow-lg:   0 16px 60px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.3);
  --shadow-card: 0 2px 12px rgba(0,0,0,0.25);
  --shadow-xl:   0 32px 80px rgba(0,0,0,0.6);

  --transition-fast:   150ms ease;
  --transition-normal: 200ms ease;
  --transition-slow:   300ms ease-out;

  /* Backward-compatible aliases (REMOVE IN PHASE 2) */
  --color-terracotta:          var(--accent);
  --color-warm-background:     var(--bg-base);
  --color-warm-surface:        var(--bg-surface);
  --color-warm-border:         var(--ink-700);
  --color-warm-text-primary:   var(--ink-100);
  --color-warm-text-secondary: var(--ink-400);
}

/* No-JS fallback: use prefers-color-scheme to set data-theme */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    --bg-base:      #100E0B;
    --bg-surface:   #171310;
    --bg-raised:    #1F1A15;
    --bg-overlay:   #28211A;
    --bg-input:     #1F1A15;
    --bg-stone:     #1C1813;
    --bg-warm:      #141109;
    --accent:         #D07050;
    --accent-light:   rgba(208,112,80,0.14);
    --accent-muted:   #8C402A;
    --accent-fg:      #E8906E;
    --gold:           #C8A96E;
    --gold-light:     rgba(200,169,110,0.12);
    --ink-100:  #F0EAE2;
    --ink-200:  #D4C8BC;
    --ink-300:  #A89484;
    --ink-400:  #7A6A5C;
    --ink-500:  #5C4E42;
    --ink-600:  #3D332A;
    --ink-700:  #2E251E;
    --ink-800:  #221C16;
    --ink-900:  #1A1410;
    --success:     #5A9E6A;
    --success-bg:  rgba(90,158,106,0.12);
    --info:        #4A84A8;
    --info-bg:     rgba(74,132,168,0.12);
    --warning:     #B8943A;
    --warning-bg:  rgba(184,148,58,0.12);
    --error:       #C25555;
    --error-bg:    rgba(194,85,85,0.12);
    --shadow-sm:   0 1px 3px rgba(0,0,0,0.3);
    --shadow-md:   0 4px 20px rgba(0,0,0,0.4);
    --shadow-lg:   0 16px 60px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.3);
    --shadow-card: 0 2px 12px rgba(0,0,0,0.25);
    --shadow-xl:   0 32px 80px rgba(0,0,0,0.6);
    --transition-fast:   150ms ease;
    --transition-normal: 200ms ease;
    --transition-slow:   300ms ease-out;
    --color-terracotta:          var(--accent);
    --color-warm-background:     var(--bg-base);
    --color-warm-surface:        var(--bg-surface);
    --color-warm-border:         var(--ink-700);
    --color-warm-text-primary:   var(--ink-100);
    --color-warm-text-secondary: var(--ink-400);
  }
}

/* Light fallback for :root without data-theme (no-JS + light preference) */
:root:not([data-theme]) {
  --bg-base:      #FAF8F5;
  --bg-surface:   #FFFFFF;
  --bg-raised:    #F3EFE9;
  --bg-overlay:   #EDE8E1;
  --bg-input:     #F3EFE9;
  --bg-stone:     #EAE4DA;
  --bg-warm:      #F5F1EB;
  --accent:         #C4694F;
  --accent-light:   #F0E0D9;
  --accent-muted:   #D4886E;
  --accent-fg:      #8C3A24;
  --gold:           #A07830;
  --gold-light:     #F5EDD8;
  --ink-100:  #1C1713;
  --ink-200:  #3A302A;
  --ink-300:  #5C5048;
  --ink-400:  #7A6E64;
  --ink-500:  #9C8E84;
  --ink-600:  #BDB0A6;
  --ink-700:  #D6CFC8;
  --ink-800:  #EAE4DE;
  --ink-900:  #F5F1EC;
  --success:     #4A8A5C;
  --success-bg:  #E0EEE5;
  --info:        #3A6A8C;
  --info-bg:     #D8E8F2;
  --warning:     #A07830;
  --warning-bg:  #F2EAD8;
  --error:       #8C2A2A;
  --error-bg:    #F5E0E0;
  --shadow-sm:   0 1px 3px rgba(28,23,19,0.06), 0 1px 2px rgba(28,23,19,0.04);
  --shadow-md:   0 4px 16px rgba(28,23,19,0.08), 0 1px 4px rgba(28,23,19,0.04);
  --shadow-lg:   0 12px 48px rgba(28,23,19,0.10), 0 2px 8px rgba(28,23,19,0.05);
  --shadow-card: 0 2px 8px rgba(28,23,19,0.06);
  --shadow-xl:   0 32px 80px rgba(28,23,19,0.12), 0 8px 24px rgba(28,23,19,0.07);
  --transition-fast:   150ms ease;
  --transition-normal: 200ms ease;
  --transition-slow:   300ms ease-out;
  --color-terracotta:          var(--accent);
  --color-warm-background:     var(--bg-base);
  --color-warm-surface:        var(--bg-surface);
  --color-warm-border:         var(--ink-700);
  --color-warm-text-primary:   var(--ink-100);
  --color-warm-text-secondary: var(--ink-400);
}

/* ================================================================
   BASE LAYER
   ================================================================ */

@layer base {
  html {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    background-color: var(--bg-base);
    color: var(--ink-100);
    font-family: var(--font-sora), system-ui, sans-serif;
    line-height: 1.6;
  }

  h1, h2, h3, h4, h5, h6 {
    font-family: var(--font-sora), system-ui, sans-serif;
    font-weight: 600;
    line-height: 1.2;
    color: var(--ink-100);
  }

  code, pre, [data-mono] {
    font-family: var(--font-dm-mono), monospace;
  }

  *:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: no-preference) {
    html {
      scroll-behavior: smooth;
    }
  }
}

/* ================================================================
   COMPONENT LAYER
   ================================================================ */

@layer components {
  .label-mono {
    font-family: var(--font-dm-mono), monospace;
    font-size: 0.625rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--ink-500);
  }

  .section-eyebrow {
    font-family: var(--font-dm-mono), monospace;
    font-size: 0.5625rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--accent);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .section-eyebrow::before {
    content: "";
    display: block;
    width: 18px;
    height: 1px;
    background: var(--accent);
  }

  .btn-primary {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem 1.25rem;
    background: var(--accent);
    color: #FFFFFF;
    font-family: var(--font-sora), system-ui, sans-serif;
    font-size: 0.875rem;
    font-weight: 600;
    border-radius: 9999px;
    box-shadow: var(--shadow-sm);
    transition: transform var(--transition-fast), box-shadow var(--transition-fast);
    white-space: nowrap;
  }

  .btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-md);
  }

  .btn-primary:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .btn-ghost {
    font-family: var(--font-dm-mono), monospace;
    font-size: 0.625rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--ink-400);
    background: none;
    border: none;
    cursor: pointer;
    transition: color var(--transition-fast);
  }

  .btn-ghost:hover {
    color: var(--ink-200);
  }

  .btn-secondary {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem 1rem;
    background: var(--bg-surface);
    color: var(--ink-100);
    font-weight: 500;
    border-radius: 0.75rem;
    border: 1px solid var(--ink-700);
    transition: background var(--transition-fast);
  }

  .btn-secondary:hover {
    background: var(--bg-raised);
  }

  .card {
    background: var(--bg-surface);
    border: 1px solid var(--ink-700);
    border-radius: 1rem;
    box-shadow: var(--shadow-card);
  }

  .chip {
    font-family: var(--font-dm-mono), monospace;
    font-size: 0.4375rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    border-radius: 9999px;
    padding: 0.25rem 0.5rem;
    min-height: 24px;
    display: inline-flex;
    align-items: center;
  }

  .chip-local {
    background: var(--success-bg);
    color: var(--success);
  }

  .chip-source {
    background: var(--info-bg);
    color: var(--info);
  }

  .chip-busy {
    background: var(--warning-bg);
    color: var(--warning);
  }

  .photo-overlay-warm {
    background: linear-gradient(
      to top,
      rgba(14,10,6,0.92) 0%,
      rgba(14,10,6,0.15) 55%,
      transparent 100%
    );
  }

  .skel {
    background: var(--ink-800);
    border-radius: 6px;
    animation: shimmer 1.5s ease-in-out infinite;
  }

  @media (prefers-reduced-motion: reduce) {
    .skel {
      animation: none;
    }
  }
}

@keyframes shimmer {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

/* ================================================================
   LEAFLET OVERRIDES
   ================================================================ */

.overplanned-map-pin {
  background: transparent !important;
  border: none !important;
}

.overplanned-popup .leaflet-popup-content-wrapper {
  background: var(--bg-surface);
  border: 1px solid var(--ink-700);
  border-radius: 0.75rem;
  box-shadow: var(--shadow-md);
  color: var(--ink-100);
  font-family: var(--font-sora), system-ui, sans-serif;
}

.overplanned-popup .leaflet-popup-tip {
  background: var(--bg-surface);
  border: 1px solid var(--ink-700);
}

.overplanned-popup .leaflet-popup-close-button {
  color: var(--ink-400);
}

.overplanned-popup .leaflet-popup-close-button:hover {
  color: var(--ink-100);
}

.scrollbar-none {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.scrollbar-none::-webkit-scrollbar {
  display: none;
}
```

**Step 4: Run test to verify it passes**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/tokens/token-resolution.test.ts`
Expected: ALL PASS

---

### Task 1.2: Rewrite Tailwind Config

**Files:**
- Modify: `apps/web/tailwind.config.ts`

**Step 1: Rewrite tailwind.config.ts**

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          100: "var(--ink-100)",
          200: "var(--ink-200)",
          300: "var(--ink-300)",
          400: "var(--ink-400)",
          500: "var(--ink-500)",
          600: "var(--ink-600)",
          700: "var(--ink-700)",
          800: "var(--ink-800)",
          900: "var(--ink-900)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          light: "var(--accent-light)",
          muted: "var(--accent-muted)",
          fg: "var(--accent-fg)",
        },
        gold: {
          DEFAULT: "var(--gold)",
          light: "var(--gold-light)",
        },
        success: { DEFAULT: "var(--success)", bg: "var(--success-bg)" },
        info: { DEFAULT: "var(--info)", bg: "var(--info-bg)" },
        warning: { DEFAULT: "var(--warning)", bg: "var(--warning-bg)" },
        error: { DEFAULT: "var(--error)", bg: "var(--error-bg)" },
        // Backward-compat aliases (REMOVE IN PHASE 2)
        terracotta: {
          DEFAULT: "var(--accent)",
        },
        warm: {
          background: "var(--bg-base)",
          surface: "var(--bg-surface)",
          border: "var(--ink-700)",
          "text-primary": "var(--ink-100)",
          "text-secondary": "var(--ink-400)",
        },
      },
      backgroundColor: {
        base: "var(--bg-base)",
        surface: "var(--bg-surface)",
        raised: "var(--bg-raised)",
        overlay: "var(--bg-overlay)",
        input: "var(--bg-input)",
        stone: "var(--bg-stone)",
        warm: "var(--bg-warm)",
        // Backward-compat aliases (REMOVE IN PHASE 2)
        app: "var(--bg-base)",
      },
      borderColor: {
        DEFAULT: "var(--ink-700)",
      },
      textColor: {
        // Backward-compat aliases (REMOVE IN PHASE 2)
        primary: "var(--ink-100)",
        secondary: "var(--ink-400)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        card: "var(--shadow-card)",
        xl: "var(--shadow-xl)",
      },
      fontFamily: {
        sora: ["var(--font-sora)", "system-ui", "sans-serif"],
        "dm-mono": ["var(--font-dm-mono)", "monospace"],
        lora: ["var(--font-lora)", "Georgia", "serif"],
      },
      keyframes: {
        "slot-reveal": {
          "0%": { opacity: "0", transform: "translateY(12px) scale(0.97)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
      },
      animation: {
        "slot-reveal": "slot-reveal 0.5s ease-out forwards",
      },
    },
  },
  plugins: [],
};

export default config;
```

**Step 2: Verify the app still builds with aliases**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx next build 2>&1 | head -20`
Expected: Build completes (may have warnings but no errors from missing classes)

---

### Task 1.3: Update Layout with Lora Font + Theme Script

**Files:**
- Modify: `apps/web/app/layout.tsx`

**Step 1: Rewrite layout.tsx**

```typescript
import type { Metadata, Viewport } from "next";
import { Sora, DM_Mono, Lora } from "next/font/google";
import { SessionProvider } from "@/components/auth/SessionProvider";
import "./globals.css";

const sora = Sora({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sora",
  weight: ["300", "400", "500", "600", "700"],
});

const dmMono = DM_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-dm-mono",
  weight: ["400", "500"],
});

const lora = Lora({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-lora",
  weight: ["400", "500"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Overplanned",
  description: "Behavioral-driven travel planning",
  metadataBase: new URL(process.env.NEXTAUTH_URL || "http://localhost:3000"),
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FAF8F5" },
    { media: "(prefers-color-scheme: dark)", color: "#100E0B" },
  ],
};

const THEME_SCRIPT = `
(function(){
  var t = localStorage.getItem('theme');
  if (!t) t = matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', t);
})()
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${sora.variable} ${dmMono.variable} ${lora.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <SessionProvider>{children}</SessionProvider>
      </body>
    </html>
  );
}
```

**Step 2: Run token tests again to confirm nothing broke**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run __tests__/tokens/`
Expected: ALL PASS

---

### Task 1.4: Create Token Swatch Dev Page

**Files:**
- Create: `apps/web/app/dev/tokens/page.tsx`

**Step 1: Create the swatch page**

```typescript
// apps/web/app/dev/tokens/page.tsx
"use client";

import { useEffect, useState } from "react";

const BG_TOKENS = ["base", "surface", "raised", "overlay", "input", "stone", "warm"];
const INK_TOKENS = [100, 200, 300, 400, 500, 600, 700, 800, 900];
const ACCENT_TOKENS = ["accent", "accent-light", "accent-muted", "accent-fg"];
const SEMANTIC = ["success", "info", "warning", "error"];

function Swatch({ label, cssVar }: { label: string; cssVar: string }) {
  return (
    <div className="flex items-center gap-3 py-1">
      <div
        className="w-10 h-10 rounded-lg border border-ink-700"
        style={{ background: `var(--${cssVar})` }}
      />
      <div>
        <div className="font-dm-mono text-[10px] text-ink-400">{`--${cssVar}`}</div>
        <div className="font-sora text-xs text-ink-200">{label}</div>
      </div>
    </div>
  );
}

export default function TokenSwatchPage() {
  const [theme, setTheme] = useState("light");

  useEffect(() => {
    setTheme(document.documentElement.getAttribute("data-theme") || "light");
  }, []);

  const toggle = () => {
    const next = theme === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    setTheme(next);
  };

  if (process.env.NODE_ENV !== "development") return null;

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8" style={{ background: "var(--bg-base)" }}>
      <div className="flex justify-between items-center">
        <h1 className="font-sora text-2xl font-bold text-ink-100">Token Swatch</h1>
        <button onClick={toggle} className="btn-primary">
          Theme: {theme}
        </button>
      </div>

      <section>
        <h2 className="section-eyebrow mb-4">Backgrounds</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {BG_TOKENS.map((t) => (
            <Swatch key={t} label={t} cssVar={`bg-${t}`} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Ink Scale (100=darkest)</h2>
        <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
          {INK_TOKENS.map((n) => (
            <Swatch key={n} label={`ink-${n}`} cssVar={`ink-${n}`} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Accent</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {ACCENT_TOKENS.map((t) => (
            <Swatch key={t} label={t} cssVar={t} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Semantic</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {SEMANTIC.map((s) => (
            <>
              <Swatch key={s} label={s} cssVar={s} />
              <Swatch key={`${s}-bg`} label={`${s}-bg`} cssVar={`${s}-bg`} />
            </>
          ))}
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Typography</h2>
        <p className="font-sora text-ink-100">Sora: Body text and UI elements</p>
        <p className="font-dm-mono text-ink-300">DM Mono: Data labels and badges</p>
        <p className="font-lora italic text-ink-200 text-lg">Lora: Serif headlines and emotional text</p>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Components</h2>
        <div className="space-y-4">
          <div className="flex gap-3">
            <button className="btn-primary">Primary Button</button>
            <button className="btn-secondary">Secondary Button</button>
            <button className="btn-ghost">Ghost Button</button>
          </div>
          <div className="flex gap-2">
            <span className="chip chip-local">Local Gem</span>
            <span className="chip chip-source">Multi Source</span>
            <span className="chip chip-busy">Peak Hours</span>
          </div>
          <div className="card p-4">
            <p className="label-mono mb-2">Card Component</p>
            <p className="text-ink-300 text-sm">A card with the design token system applied.</p>
          </div>
        </div>
      </section>

      <section>
        <h2 className="section-eyebrow mb-4">Shadows</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {["sm", "md", "lg", "card", "xl"].map((s) => (
            <div
              key={s}
              className="p-4 rounded-xl bg-surface text-center text-ink-300 font-dm-mono text-xs"
              style={{ boxShadow: `var(--shadow-${s})` }}
            >
              shadow-{s}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
```

---

### Task 1.5: Commit Phase 1

**Step 1: Run all tests**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx vitest run`
Expected: ALL PASS

**Step 2: Verify dev server loads without errors**

Run: `cd /home/pogchamp/Desktop/overplanned/apps/web && npx next build 2>&1 | tail -5`
Expected: Build succeeds

**Step 3: Commit**

```bash
cd /home/pogchamp/Desktop/overplanned
git add apps/web/app/globals.css apps/web/tailwind.config.ts apps/web/app/layout.tsx apps/web/app/dev/tokens/page.tsx apps/web/__tests__/tokens/ CLAUDE.md
git commit -m "feat(web): Phase 1 — token foundation, theme system, Lora font, backward-compat aliases"
```

---

## Phase 2: Core Components

> Phase 2 is a large atomic commit. The detailed task breakdown for Phase 2 covers:
> 1. Breakage inventory + bulk token migration across all 50 files
> 2. SlotCard rewrite to match design-v4.html
> 3. Skeleton/Empty/Error state components
> 4. AppShell + Navigation rewrite
> 5. Remove backward-compatible aliases
> 6. Tests for all components

### Task 2.1: Breakage Inventory + Bulk Token Migration

**Files:**
- Modify: ALL 50 files listed in the explore report (see design doc for full list)

**Step 1: Run grep to identify all old token usage**

Run:
```bash
cd /home/pogchamp/Desktop/overplanned/apps/web && grep -rn "warm-surface\|warm-background\|warm-border\|warm-text-primary\|warm-text-secondary\|bg-app\|text-primary\|text-secondary\|border-warm\|terracotta\|amber-\|emerald-\|gray-100\|gray-400\|gray-500" --include="*.tsx" --include="*.ts" | grep -v node_modules | grep -v __tests__ | wc -l
```

Record the count. This is the number of lines to migrate.

**Step 2: Bulk find-replace across all files**

Token migration map (old -> new):

| Old Class | New Class |
|-----------|-----------|
| `bg-warm-surface` | `bg-surface` |
| `bg-warm-background` | `bg-base` |
| `bg-app` | `bg-base` |
| `text-warm-text-primary` | `text-ink-100` |
| `text-warm-text-secondary` | `text-ink-400` |
| `text-primary` (in className) | `text-ink-100` |
| `text-secondary` (in className) | `text-ink-400` |
| `border-warm-border` | `border-ink-700` |
| `border-warm` | `border-ink-700` |
| `bg-terracotta` | `bg-accent` |
| `text-terracotta` | `text-accent` |
| `hover:bg-terracotta-600` | `hover:bg-accent/90` |
| `ring-terracotta` | `ring-accent` |
| `bg-amber-50` | `bg-warning-bg` |
| `bg-amber-400` | `bg-warning` |
| `text-amber-700` | `text-warning` |
| `text-amber-600` | `text-warning` |
| `bg-emerald-50` | `bg-success-bg` |
| `bg-emerald-400` | `bg-success` |
| `text-emerald-700` | `text-success` |
| `bg-gray-100` | `bg-ink-800` |
| `bg-gray-400` | `bg-ink-600` |
| `text-gray-500` | `text-ink-500` |
| `text-gray-400` | `text-ink-600` |
| `bg-red-50` | `bg-error-bg` |
| `text-red-600` | `text-error` |

Execute the migration using sed or manual edits per file. Each file gets its class names updated to the new token vocabulary.

**Step 3: Remove backward-compatible aliases from globals.css**

Remove all lines containing `/* Backward-compatible aliases */` and the alias declarations from both light and dark theme blocks, and the `:root:not([data-theme])` fallback blocks.

**Step 4: Remove backward-compat entries from tailwind.config.ts**

Remove the `terracotta`, `warm`, `bg-app`, `text-primary`, `text-secondary` compatibility entries.

**Step 5: Verify zero old tokens remain**

Run:
```bash
cd /home/pogchamp/Desktop/overplanned/apps/web && grep -rn "warm-surface\|warm-background\|warm-border\|warm-text-primary\|warm-text-secondary\|bg-app\|terracotta\|amber-50\|amber-400\|amber-700\|emerald-50\|emerald-400\|emerald-700\|gray-100\|gray-400\|gray-500" --include="*.tsx" --include="*.ts" --include="*.css" | grep -v node_modules | grep -v __tests__
```
Expected: 0 results

---

### Task 2.2: SlotCard Rewrite

**Files:**
- Modify: `apps/web/components/slot/SlotCard.tsx`
- Modify: `apps/web/__tests__/solo/SlotCard.test.tsx`

Rewrite SlotCard to match overplanned-solo-view.html mockup:
- Add `whyThis?: string` optional prop
- Replace STATUS_CONFIG to use semantic tokens (success, warning, ink)
- Add warm photo overlay
- Add `will-change: transform` on hover scale
- Use new token classes throughout
- Add `whyThis` italic line below activity name

Full implementation code should match the design doc Phase 2 SlotCard spec.

### Task 2.3: Skeleton / Empty / Error State Components

**Files:**
- Create: `apps/web/components/states/SlotSkeleton.tsx`
- Create: `apps/web/components/states/CardSkeleton.tsx`
- Create: `apps/web/components/states/EmptyState.tsx`
- Create: `apps/web/components/states/ErrorState.tsx`
- Create: `apps/web/__tests__/states/`

Match overplanned-states.html mockup patterns. Use Lora for empty state titles, shimmer animation with prefers-reduced-motion support.

### Task 2.4: AppShell + Navigation Rewrite

**Files:**
- Modify: `apps/web/components/layout/AppShell.tsx`
- Modify: `apps/web/components/nav/MobileNav.tsx`
- Modify: `apps/web/components/nav/DesktopSidebar.tsx`

Implement two navigation contexts:
- App context: bottom nav (Home/Trips/Explore/Profile) with DM Mono labels
- Trip context: hero photo + day strip, no bottom nav
- Wordmark: Sora 700, letter-spacing -0.04em, accent on "."

### Task 2.5: Phase 2 Tests + Commit

Run full test suite, verify all 48 SlotCard render cases, interaction tests, accessibility (axe-core), then commit.

```bash
git commit -m "feat(web): Phase 2 — component rewrite, token migration (50 files), remove backward-compat aliases"
```

---

## Phase 3+4: Screens + API (Interleaved)

### Task 3.1: Landing Page

**Files:**
- Modify: `apps/web/app/page.tsx`
- Create: `apps/web/components/landing/Globe.tsx` (lazy-loaded)
- Create: `apps/web/components/landing/Hero.tsx`
- Create: `apps/web/components/landing/Features.tsx`
- Create: `apps/web/components/landing/Nav.tsx`

Match overplanned-landing.html. Lora headlines, gold `<em>` accents, Sora wordmark. Globe lazy-loaded with `next/dynamic({ ssr: false })` + IntersectionObserver. Mobile fallback banner under 900px.

### Task 3.2: Schema Migration

**Files:**
- Modify: `prisma/schema.prisma`

Add `name String?` to Trip model. Run `prisma migrate dev --name add_trip_name`.

### Task 3.3: Trip CRUD API Routes

**Files:**
- Create: `apps/web/app/api/trips/route.ts` (POST + GET)
- Create: `apps/web/app/api/trips/[id]/route.ts` (GET + PATCH)
- Create: `apps/web/lib/validations/trip.ts` (Zod schemas)
- Create: `apps/web/__tests__/api/trips.test.ts`

All routes use getServerSession for auth. GET endpoints filter by TripMember. PATCH requires organizer role. Zod validation on POST/PATCH bodies.

### Task 3.4: Onboarding Screen

**Files:**
- Modify: `apps/web/app/onboarding/page.tsx`
- Modify: `apps/web/app/onboarding/components/ForkScreen.tsx`
- Modify: `apps/web/app/onboarding/components/DestinationStep.tsx`
- Modify: `apps/web/app/onboarding/components/DatesStep.tsx`
- Modify: `apps/web/app/onboarding/components/TripDNAStep.tsx`
- Create: `apps/web/__tests__/e2e/onboarding.spec.ts`

Wire to POST /api/trips. Redirect to trip detail on success. Match overplanned-onboarding.html mockup.

### Task 3.5: Home Dashboard

**Files:**
- Create: `apps/web/app/dashboard/page.tsx` (or modify existing home)
- Create: `apps/web/components/dashboard/TripHeroCard.tsx`
- Create: `apps/web/components/dashboard/PastTripRow.tsx`

Match overplanned-app-shell.html home screen. Uses GET /api/trips. Empty state for no trips.

### Task 3.6: Trip Detail / Solo View

**Files:**
- Modify: `apps/web/app/trip/[id]/page.tsx`
- Modify: `apps/web/components/trip/DayView.tsx`
- Modify: `apps/web/components/trip/DayNavigation.tsx`

Remove all hardcoded MOCK_TRIP and MOCK_SLOTS. Fetch from GET /api/trips/[id]. Match overplanned-solo-view.html. Hero with warm overlay, day strip, energy bar, real SlotCard data.

### Task 3.7: Phase 3+4 Commit

Run all unit + E2E tests. Verify onboarding creates real trips, dashboard shows them, trip detail loads real data.

```bash
git commit -m "feat(web): Phase 3+4 — landing page, trip CRUD API, onboarding, dashboard, trip detail with real data"
```

---

## File Inventory Summary

| Phase | Files Created | Files Modified | Tests Created |
|-------|--------------|----------------|---------------|
| 0 | 6 | 2 | 1 |
| 1 | 2 | 3 | 1 |
| 2 | 4 | ~50 | 4+ |
| 3+4 | 8 | 12 | 3+ |
| **Total** | **~20** | **~67** | **~9+** |

---

## Key References

- **Design doc:** `docs/plans/2026-02-20-ui-overhaul-design.md`
- **HTML mockups:** `docs/overplanned-*.html` (22 files)
- **Design system canonical:** `docs/overplanned-design-v4.html`
- **Philosophy:** `docs/overplanned-philosophy.md`
- **Navigation architecture:** `docs/overplanned-navigation-architecture.md`
- **Prisma schema:** `prisma/schema.prisma`
