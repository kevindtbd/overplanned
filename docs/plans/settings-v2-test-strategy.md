# Settings V2 — Test Strategy

Vitest + React Testing Library throughout. No Jest. Matches existing conventions in the
`__tests__/` tree: `vi.mock`, `vi.fn()`, `vi.useFakeTimers`, `userEvent.setup()`,
`act + advanceTimersByTimeAsync` for debounce, `aria-checked` assertions for toggles.

---

## File Map

| Area | File path |
|---|---|
| DisplayPreferences component | `apps/web/__tests__/settings/DisplayPreferences.test.tsx` |
| TravelInterests component | `apps/web/__tests__/settings/TravelInterests.test.tsx` |
| Billing portal API route | `apps/web/__tests__/api/settings-billing-portal.test.ts` |
| Notifications enhancements | extend `apps/web/__tests__/api/settings-notifications.test.ts` |
| NotificationsSection enhancements | extend `apps/web/__tests__/settings/NotificationsSection.test.tsx` |
| Theme cookie — layout | `apps/web/__tests__/settings/theme-cookie.test.ts` |
| Consumer wiring — .ics export | extend `apps/web/__tests__/lib/ics-export.test.ts` |
| Consumer wiring — slot time display | `apps/web/__tests__/settings/display-format-consumers.test.ts` |
| Preferences API enhancements | extend `apps/web/__tests__/api/settings-preferences.test.ts` |
| SettingsPage (mocks for new sections) | extend `apps/web/__tests__/settings/SettingsPage.test.tsx` |

---

## 1. DisplayPreferences Component

**File:** `apps/web/__tests__/settings/DisplayPreferences.test.tsx`

### Mocking pattern

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DisplayPreferences } from "@/components/settings/DisplayPreferences";

const GET_DEFAULTS = {
  distanceUnit: "mi",
  temperatureUnit: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
};

function mockFetchSuccess(getData = GET_DEFAULTS) {
  const fetchMock = vi.fn();
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => getData,
  });
  // Subsequent PATCH calls succeed
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => getData,
  });
  global.fetch = fetchMock;
  return fetchMock;
}

// Theme cookie setter — document.cookie is a live setter, spy on it
function mockDocumentCookie() {
  const cookieSpy = vi.spyOn(document, "cookie", "set");
  return cookieSpy;
}

// document.documentElement.setAttribute spy for data-theme mutations
function mockHtmlAttribute() {
  return vi.spyOn(document.documentElement, "setAttribute");
}
```

### Tests

**Load + skeleton**

- `renders skeleton (animate-pulse) while GET is in-flight, then shows radio groups after load`
  - Assert `container.querySelector(".animate-pulse")` exists before, then absent after `waitFor`

- `all 5 radio groups render after load: Distance, Temperature, Date format, Time format, Theme`
  - Assert headings/labels for each group are in document

**Happy-path radio selection — Distance**

- `selecting "km" sends PATCH { distanceUnit: "km" } immediately (no debounce)`
  - `userEvent.click` the "km" radio
  - `await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))`
  - Assert body: `JSON.parse(patchCall[1].body)` equals `{ distanceUnit: "km" }`

- `the selected radio pill has aria-checked="true", deselected one has aria-checked="false"`
  - After clicking "km": `expect(screen.getByRole("radio", { name: "km" })).toHaveAttribute("aria-checked", "true")`
  - `expect(screen.getByRole("radio", { name: "mi" })).toHaveAttribute("aria-checked", "false")`

**Happy-path radio selection — Temperature**

- `selecting "C" sends PATCH { temperatureUnit: "C" } immediately`
  - Same assertion pattern as distance

**Happy-path radio selection — Date format**

- `selecting "DD/MM/YYYY" sends PATCH { dateFormat: "DD/MM/YYYY" } immediately`
- `selecting "YYYY-MM-DD" sends PATCH { dateFormat: "YYYY-MM-DD" } immediately`
- Three-option group: assert the active radio pill has `aria-checked="true"` and the other two have `aria-checked="false"`

**Happy-path radio selection — Time format**

- `selecting "24h" sends PATCH { timeFormat: "24h" } immediately`

**Theme — DOM mutation**

- `selecting "dark" calls document.documentElement.setAttribute("data-theme", "dark")`
  - Mock `setAttribute` spy, click "dark" radio, assert spy called with `("data-theme", "dark")`

- `selecting "light" calls document.documentElement.setAttribute("data-theme", "light")`

- `selecting "system" calls document.documentElement.removeAttribute("data-theme")`
  - Spy on `removeAttribute` instead; assert called with `"data-theme"`

**Theme — cookie persistence**

- `selecting "dark" sets document.cookie to "theme=dark;path=/;max-age=31536000"`
  - `cookieSpy = mockDocumentCookie()`
  - After click: `expect(cookieSpy).toHaveBeenCalledWith("theme=dark;path=/;max-age=31536000")`

- `selecting "system" sets document.cookie to "theme=system;path=/;max-age=31536000"`

**Revert on failure**

- `reverts radio selection when PATCH returns ok: false`
  - Load with `distanceUnit: "mi"`; PATCH mocked to `{ ok: false }`
  - Click "km" → PATCH fires → assert "mi" radio returns to `aria-checked="true"`, "km" returns to `aria-checked="false"` after `waitFor`

- `reverts radio selection when PATCH throws (network error)`
  - PATCH mock: `fetchMock.mockRejectedValueOnce(new Error("Network error"))`
  - Same revert assertion

**GET failure**

- `shows error state when GET fails, renders no radio groups`
  - `global.fetch = vi.fn().mockResolvedValueOnce({ ok: false })`
  - `await waitFor(() => expect(screen.getByText(/failed to load/i)).toBeInTheDocument())`
  - `expect(screen.queryAllByRole("radio")).toHaveLength(0)`

**Initial state from saved prefs**

- `loads saved preferences and marks correct radios as selected`
  - `getData = { ...GET_DEFAULTS, distanceUnit: "km", theme: "dark", timeFormat: "24h" }`
  - After load: assert "km", "dark", "24h" each have `aria-checked="true"`

**Rapid clicks**

- `rapid clicks on same group fire exactly 1 PATCH (last value wins, no debounce needed — but no duplicate in-flight)`
  - Note: DisplayPreferences has no debounce (unlike chips). Each click fires immediately. Rapid
    clicks on the same group should each fire, but the last one represents final state. Test
    that the component doesn't send duplicate calls for the same value:
  - Click "km" then "mi" in rapid succession; assert two PATCHes total (one per change), not three.

---

## 2. TravelInterests Component

**File:** `apps/web/__tests__/settings/TravelInterests.test.tsx`

### Mocking pattern

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TravelInterests } from "@/components/settings/TravelInterests";

const GET_DEFAULTS = {
  vibePreferences: [],
  travelStyleNote: null,
};

function mockFetchSuccess(getData = GET_DEFAULTS) {
  const fetchMock = vi.fn();
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => getData,
  });
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => getData,
  });
  global.fetch = fetchMock;
  return fetchMock;
}

async function renderAndLoad(getData = GET_DEFAULTS) {
  const fetchMock = mockFetchSuccess(getData);
  vi.useFakeTimers();
  await act(async () => { render(<TravelInterests />); });
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  // Verify load completed — first chip group label should be visible
  expect(screen.getByText("Pace & Energy")).toBeInTheDocument();
  return fetchMock;
}
```

### Tests

**Load + skeleton**

- `renders skeleton while GET is in-flight, then chip groups after load`
  - Assert `.animate-pulse` exists then absent

- `renders all 5 chip group headings: Pace & Energy, Discovery Style, Food & Drink, Activity Type, Social & Time`

- `renders all 23 chip labels`
  - Use `screen.getByText` for a sample across groups:
    `"High energy"`, `"Hidden gems"`, `"Street food"`, `"Urban exploration"`, `"Solo-friendly"`

**Chip selection — debounce**

- `clicking a chip optimistically adds terracotta fill class, triggers PATCH after 500ms`
  - Click "Street food" chip
  - Assert chip immediately shows active state (check for class or `aria-pressed="true"` depending on implementation)
  - Assert `fetchMock` called 1 time (GET only) before `advanceTimersByTimeAsync(499)`
  - After `advanceTimersByTimeAsync(501)`: assert `fetchMock` called 2 times
  - Assert PATCH body: `{ vibePreferences: ["street-food"] }`

- `rapid chip clicks within 500ms fire exactly 1 PATCH with final state`
  - Click "High energy" (t=0), "Hidden gems" (t=100ms), "Street food" (t=200ms)
  - `advanceTimersByTimeAsync(500)` from last click
  - Count PATCH calls: exactly 1
  - Body contains all three tags: `["high-energy", "hidden-gem", "street-food"]`

- `clicking active chip deselects it, PATCH fires after 500ms without that tag`
  - Load with `vibePreferences: ["street-food"]`
  - Assert "Street food" chip renders with active state initially
  - Click it → `advanceTimersByTimeAsync(500)` → assert PATCH body `vibePreferences: []`

**Multi-select — no min/max enforcement**

- `selecting all 23 chips sends PATCH with all 23 slugs`
  - Click all 23 chips in sequence, advance 500ms, assert `vibePreferences.length === 23`
  - Note: Test 5-6 representative chips to keep test readable, not all 23

**Revert on chip failure**

- `reverts chip selection when PATCH returns ok: false`
  - Load with empty prefs; PATCH mocked to fail
  - Click "Street food" → advance 500ms → await PATCH failure → assert chip returns to inactive state
  - Specifically: `expect(chip).not.toHaveAttribute("aria-pressed", "true")` (or whatever active class)

- `reverts chip deselection when PATCH fails`
  - Load with `vibePreferences: ["street-food"]`; PATCH mocked to fail
  - Click "Street food" to deselect → PATCH fails → assert chip remains active

**Textarea — save on blur**

- `textarea does NOT fire PATCH during typing (no debounce, waits for blur)`
  - `userEvent.type(textarea, "I love coffee shops")` without blur
  - `await vi.advanceTimersByTimeAsync(1000)` — even 1s of waiting should not fire PATCH
  - Assert `fetchMock` still at 1 call (GET only)

- `textarea fires PATCH with travelStyleNote on blur`
  - `await userEvent.type(textarea, "I love coffee shops")`
  - `await userEvent.tab()` — triggers blur
  - `await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))`
  - Assert PATCH body: `{ travelStyleNote: "I love coffee shops" }`

- `textarea does NOT fire PATCH on blur when value is unchanged`
  - Load with `travelStyleNote: "existing note"`
  - Click textarea (focus), then tab (blur) without typing
  - Assert `fetchMock` called 1 time (GET only, no PATCH)

- `textarea reverts to previous value on PATCH failure`
  - Load with `travelStyleNote: "original note"`; PATCH mocked to fail
  - Type "new note", blur → after PATCH failure → `expect(textarea).toHaveValue("original note")`

- `textarea reverts on network error (fetch throws)`
  - Same as above but `fetchMock.mockRejectedValueOnce(new Error("Network error"))`

**Character count**

- `character count does NOT appear when input is <= 400 chars`
  - Type 100 chars, assert count label not in document

- `character count appears when input exceeds 400 chars`
  - Type 401 chars (use `userEvent.type` with a 401-char string)
  - Assert something matching `/\d+\s*\/\s*500/` is in document (e.g. "401 / 500")

- `character count shows 500 / 500 at max`
  - Type exactly 500 chars; assert count renders

**Maxlength enforcement**

- `textarea has maxLength attribute of 500`
  - `expect(screen.getByRole("textbox")).toHaveAttribute("maxlength", "500")`

**Group structure**

- `each of the 5 groups renders its label as a section heading`
  - Use `screen.getByText("Pace & Energy")` etc. — assert role or tag is heading-like

**GET failure**

- `shows error state when GET fails, renders no chips`
  - `global.fetch = vi.fn().mockResolvedValueOnce({ ok: false })`
  - `await waitFor(() => expect(screen.getByText(/failed to load/i)).toBeInTheDocument())`
  - `expect(screen.queryByText("Street food")).not.toBeInTheDocument()`

---

## 3. Billing Portal API Route

**File:** `apps/web/__tests__/api/settings-billing-portal.test.ts`

### Mocking pattern

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

vi.mock("next-auth", () => ({
  getServerSession: vi.fn(),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: vi.fn(),
    },
  },
}));

vi.mock("@/lib/auth/config", () => ({
  authOptions: {},
}));

// Mock stripe — the module returns a constructor; mock the instance methods
vi.mock("stripe", () => {
  const mockCreate = vi.fn();
  return {
    default: vi.fn().mockImplementation(() => ({
      billingPortal: {
        sessions: {
          create: mockCreate,
        },
      },
    })),
    __mockCreate: mockCreate, // expose for assertions
  };
});

const { getServerSession } = await import("next-auth");
const { prisma } = await import("@/lib/prisma");
const { POST } = await import("../../app/api/settings/billing-portal/route");

const mockGetServerSession = vi.mocked(getServerSession);
const mockPrisma = vi.mocked(prisma);

// Access stripe mock — pattern depends on how route imports stripe
// Alternative: mock at process.env level and verify the route call via Prisma assertions
// The key is: mock stripe.billingPortal.sessions.create and assert it was called with correct customer ID

function makePostRequest(): NextRequest {
  return new NextRequest("http://localhost:3000/api/settings/billing-portal", {
    method: "POST",
  });
}

const authedSession = { user: { id: "user-abc", email: "test@example.com" } };
```

### Tests

**Auth guards**

- `returns 401 when session is null`
  - `mockGetServerSession.mockResolvedValueOnce(null)`
  - `expect((await POST(makePostRequest())).status).toBe(401)`

- `returns 401 when session has no user`
  - `mockGetServerSession.mockResolvedValueOnce({ user: null } as never)`

**No stripeCustomerId — 404**

- `returns 404 when user has no stripeCustomerId (beta user)`
  - `mockPrisma.user.findUnique.mockResolvedValueOnce({ id: "user-abc", stripeCustomerId: null } as never)`
  - `expect(res.status).toBe(404)`
  - `const json = await res.json(); expect(json.error).toMatch(/no billing/i)` (or similar friendly message)

- `returns 404 when user record is not found in DB`
  - `mockPrisma.user.findUnique.mockResolvedValueOnce(null)`
  - `expect(res.status).toBe(404)`

**Happy path — session creation**

- `returns 200 with { url } when stripeCustomerId exists and Stripe session creates successfully`
  - `mockPrisma.user.findUnique.mockResolvedValueOnce({ id: "user-abc", stripeCustomerId: "cus_abc123" } as never)`
  - Stripe mock: `mockCreate.mockResolvedValueOnce({ url: "https://billing.stripe.com/session/abc" })`
  - `expect(res.status).toBe(200)`
  - `const json = await res.json(); expect(json.url).toBe("https://billing.stripe.com/session/abc")`

- `calls stripe.billingPortal.sessions.create with correct customer and return_url`
  - Assert `mockCreate` called with:
    ```typescript
    expect(mockCreate).toHaveBeenCalledWith({
      customer: "cus_abc123",
      return_url: expect.stringContaining("/settings"),
    });
    ```

- `return_url contains NEXTAUTH_URL base (not hardcoded domain)`
  - Set `process.env.NEXTAUTH_URL = "https://app.overplanned.com"` in test
  - Assert `mockCreate` called with `return_url: "https://app.overplanned.com/settings"`

**Stripe error handling**

- `returns 500 when Stripe throws an error`
  - `mockCreate.mockRejectedValueOnce(new Error("Stripe unavailable"))`
  - `expect(res.status).toBe(500)`
  - Response body should not leak Stripe internals: `expect(json.error).not.toContain("Stripe")`
    or assert it returns a generic `"Internal server error"` message

**Field whitelisting**

- `DB lookup uses userId from session, not from request body`
  - The POST route has no body to read (billing portal requires no client input beyond auth)
  - Assert `mockPrisma.user.findUnique` called with `{ where: { id: "user-abc" } }`
  - This is the IDOR check: no request body field can influence which user record is fetched

---

## 4. Notification Enhancements

### 4a. API route extensions

**Extend:** `apps/web/__tests__/api/settings-notifications.test.ts`

Add these describe blocks after the existing ones.

**Updated DEFAULTS constant** — add to the existing `DEFAULTS` at top of file:
```typescript
const DEFAULTS = {
  // ...existing 7 fields...
  checkinReminder: false,
  preTripDaysBefore: 3,
};
```

**Also update the existing field-count assertion** at the bottom of the whitelisting describe:
```typescript
// Was: "returns only the 7 boolean notification fields"
// Update to: "returns all 9 notification fields"
const expectedKeys = [
  "tripReminders", "morningBriefing", "groupActivity",
  "postTripPrompt", "citySeeded", "inspirationNudges",
  "productUpdates", "checkinReminder", "preTripDaysBefore",
];
```

**New describe blocks to add:**

```
describe("PATCH /api/settings/notifications — checkinReminder", () => {
```

- `accepts checkinReminder: true and upserts correctly`
  - `res = await PATCH(makePatchRequest({ checkinReminder: true }))`
  - Assert `upsertCall.update` equals `{ checkinReminder: true }`
  - Assert `upsertCall.create` contains `{ userId: "user-abc", checkinReminder: true }`
  - Assert `res.status === 200`

- `accepts checkinReminder: false (opt-in default is false — must not be treated as absent)`
  - `await PATCH(makePatchRequest({ checkinReminder: false }))`
  - Assert `upsertCall.update.checkinReminder === false`
  - This mirrors the existing `inspirationNudges: false` test pattern exactly

- `returns 400 when checkinReminder receives a non-boolean string`
  - `await PATCH(makePatchRequest({ checkinReminder: "yes" }))`
  - `expect(res.status).toBe(400)`
  - `expect(json.error).toBe("Validation failed")`

```
describe("PATCH /api/settings/notifications — preTripDaysBefore", () => {
```

- `accepts preTripDaysBefore: 1 and upserts`
  - `await PATCH(makePatchRequest({ preTripDaysBefore: 1 }))`
  - `expect(upsertCall.update).toEqual({ preTripDaysBefore: 1 })`

- `accepts preTripDaysBefore: 3 and upserts`

- `accepts preTripDaysBefore: 7 and upserts`

- `returns 400 for preTripDaysBefore: 2 (not in [1, 3, 7])`
  - `expect(res.status).toBe(400)`
  - `expect(json.error).toBe("Validation failed")`

- `returns 400 for preTripDaysBefore: 0`

- `returns 400 for preTripDaysBefore: "3" (string instead of number)`

- `returns 400 for preTripDaysBefore: 3.5 (non-integer)`

```
describe("GET /api/settings/notifications — returns new fields", () => {
```

- `returns checkinReminder: false and preTripDaysBefore: 3 in defaults when no record exists`
  - `mockPrisma.notificationPreference.findUnique.mockResolvedValueOnce(null as never)`
  - `json = await res.json()`
  - `expect(json.checkinReminder).toBe(false)`
  - `expect(json.preTripDaysBefore).toBe(3)`

- `returns saved checkinReminder and preTripDaysBefore from DB record`
  - `savedPrefs = { ...DEFAULTS, checkinReminder: true, preTripDaysBefore: 7 }`
  - `expect(json.checkinReminder).toBe(true)`
  - `expect(json.preTripDaysBefore).toBe(7)`

### 4b. NotificationsSection component extensions

**Extend:** `apps/web/__tests__/settings/NotificationsSection.test.tsx`

**Updated GET_DEFAULTS** — add at top:
```typescript
const GET_DEFAULTS = {
  // ...existing 7 fields...
  checkinReminder: false,
  preTripDaysBefore: 3,
};
```

**Update existing toggle count test:**
```typescript
// Was: "renders skeleton during load, then toggles after GET resolves" — checks toHaveLength(7)
// Update to toHaveLength(8) — checkinReminder adds one more toggle
```

**Update existing "all 7 toggles" test** to "all 8 toggles" and add:
```typescript
// toggles[7] = checkinReminder (false)
expect(toggles[7]).toHaveAttribute("aria-checked", "false");
```

**New describe blocks to add:**

```
describe("NotificationsSection — checkinReminder toggle", () => {
```

- `checkinReminder renders with aria-checked="false" by default`
  - After load, find toggle by label "Check-in prompts during active trips"
  - `expect(toggle).toHaveAttribute("aria-checked", "false")`

- `clicking checkinReminder flips aria-checked to "true" optimistically`
  - `await user.click(checkinReminderToggle)`
  - `expect(checkinReminderToggle).toHaveAttribute("aria-checked", "true")`

- `clicking checkinReminder sends PATCH with { checkinReminder: true }`
  - Assert PATCH body: `expect(body).toEqual({ checkinReminder: true })`
  - Note: same immediate-PATCH pattern as other toggles (no debounce)

- `reverts checkinReminder on PATCH failure`
  - PATCH mocked to `{ ok: false }`, click toggle
  - `await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "false"))` — reverts

```
describe("NotificationsSection — preTripDaysBefore selector", () => {
```

- `preTripDaysBefore selector is visible when tripReminders is true`
  - Load with `tripReminders: true`
  - `expect(screen.getByText("Remind me before trips")).toBeInTheDocument()`
  - Assert all three option labels visible: "1 day", "3 days", "1 week"

- `preTripDaysBefore selector is hidden when tripReminders is false`
  - Load with `tripReminders: false, preTripDaysBefore: 3`
  - `expect(screen.queryByText("Remind me before trips")).not.toBeInTheDocument()`

- `preTripDaysBefore selector becomes visible when tripReminders is toggled on`
  - Load with `tripReminders: false`
  - Confirm selector absent: `expect(screen.queryByText("1 day")).not.toBeInTheDocument()`
  - Click tripReminders toggle (turns it on)
  - `await waitFor(() => expect(screen.getByText("1 day")).toBeInTheDocument())`

- `preTripDaysBefore selector hides when tripReminders is toggled off`
  - Load with `tripReminders: true`
  - Confirm selector visible
  - Click tripReminders toggle (turns it off)
  - `await waitFor(() => expect(screen.queryByText("1 day")).not.toBeInTheDocument())`

- `selected option has aria-checked="true", others have aria-checked="false" (default: 3 days)`
  - Load with `tripReminders: true, preTripDaysBefore: 3`
  - `expect(screen.getByRole("radio", { name: "3 days" })).toHaveAttribute("aria-checked", "true")`
  - `expect(screen.getByRole("radio", { name: "1 day" })).toHaveAttribute("aria-checked", "false")`
  - `expect(screen.getByRole("radio", { name: "1 week" })).toHaveAttribute("aria-checked", "false")`

- `clicking "1 week" sends PATCH { preTripDaysBefore: 7 } immediately`
  - `await user.click(screen.getByRole("radio", { name: "1 week" }))`
  - Assert PATCH body: `{ preTripDaysBefore: 7 }`

- `clicking "1 day" sends PATCH { preTripDaysBefore: 1 } immediately`

- `reverts preTripDaysBefore selection on PATCH failure`
  - Load with `tripReminders: true, preTripDaysBefore: 3`; PATCH mocked to fail
  - Click "1 week" → PATCH fails → assert "3 days" radio returns to `aria-checked="true"`

- `preTripDaysBefore value is preserved in DB when tripReminders is toggled off then on`
  - This is a UI/state test, not DB: load with `preTripDaysBefore: 7, tripReminders: true`
  - Toggle tripReminders off (selector hides), toggle on again (selector shows)
  - Assert "1 week" still has `aria-checked="true"` — value was not reset by hide/show

---

## 5. Theme Cookie — Server-Side Layout

**File:** `apps/web/__tests__/settings/theme-cookie.test.ts`

This is a pure utility test — it does not mount a React component. Tests the helper
function that reads the theme cookie server-side (extracted from `layout.tsx`).

```typescript
import { describe, it, expect } from "vitest";
import { resolveThemeFromCookie } from "@/lib/theme-cookie";
// OR if the logic lives inline in layout.tsx, extract it to a testable pure function first
```

### Tests

- `returns "light" when cookie is "theme=light"`
  - `expect(resolveThemeFromCookie("theme=light")).toBe("light")`

- `returns "dark" when cookie is "theme=dark"`

- `returns "system" when cookie is "theme=system"`

- `returns "system" when cookie string is empty`

- `returns "system" when cookie string is undefined`

- `returns "system" for unrecognized theme value "blue"`
  - Guards against injection of arbitrary attribute values

- `returns "system" when theme cookie is absent but other cookies exist`
  - `resolveThemeFromCookie("session=abc; other=xyz")` → `"system"`

- `parses theme correctly when it appears mid-string with other cookies`
  - `resolveThemeFromCookie("session=abc; theme=dark; other=xyz")` → `"dark"`

**Note on layout.tsx integration:** The actual `data-theme` attribute rendering on `<html>`
is tested at the component level only if layout.tsx can be unit-tested in isolation. If it
cannot (due to Next.js app router constraints), the above pure function tests are sufficient.
Add an E2E note in the strategy for visual regression.

---

## 6. Consumer Wiring — .ics Export

**Extend:** `apps/web/__tests__/lib/ics-export.test.ts`

The existing tests treat `generateIcsCalendar` as format-agnostic (always 24h, always
ISO dates). The new requirement: the function (or a wrapper) accepts `dateFormat` and
`timeFormat` preferences and formats DESCRIPTION / SUMMARY annotation lines accordingly.

Assumption: the function signature becomes
`generateIcsCalendar(trip, prefs?: { dateFormat?: string; timeFormat?: string })`.
The DTSTART/DTEND lines remain in RFC 5545 format regardless (the spec mandates it).
The prefs affect human-readable annotation lines only (e.g. a DESCRIPTION line that
says "09:00 AM — Tsukiji Market" vs "09:00 — Tsukiji Market").

**New describe block:**

```
describe("generateIcsCalendar — display format preferences", () => {
```

- `uses 12h time format in human-readable DESCRIPTION when timeFormat is "12h"`
  - Generate with `prefs: { timeFormat: "12h" }` and a slot with `startTime: "09:00"`
  - Assert `result` contains `"9:00 AM"` in DESCRIPTION line

- `uses 24h time format in DESCRIPTION when timeFormat is "24h"`
  - Same slot, `prefs: { timeFormat: "24h" }`
  - Assert `result` contains `"09:00"` in DESCRIPTION line

- `DTSTART and DTEND remain in RFC 5545 format (Thhmmss) regardless of timeFormat`
  - Assert `result` always contains `"DTSTART;TZID=Asia/Tokyo:20260701T090000"` regardless of `prefs`
  - The RFC format is non-negotiable — this test guards against accidentally formatting DTSTART

- `uses MM/DD/YYYY in DESCRIPTION date annotation when dateFormat is "MM/DD/YYYY"`
  - Slot on 2026-07-01; assert DESCRIPTION contains `"07/01/2026"`

- `uses DD/MM/YYYY in DESCRIPTION date annotation when dateFormat is "DD/MM/YYYY"`
  - Assert DESCRIPTION contains `"01/07/2026"`

- `uses YYYY-MM-DD in DESCRIPTION date annotation when dateFormat is "YYYY-MM-DD"`
  - Assert DESCRIPTION contains `"2026-07-01"`

- `falls back to MM/DD/YYYY and 12h when no prefs provided (backward compatibility)`
  - Call `generateIcsCalendar(trip)` with no second argument
  - Existing tests should still pass — this test explicitly documents the fallback

**If the design wraps rather than extends `generateIcsCalendar`:**

Add a new `describe("formatSlotTime", ...)` and `describe("formatSlotDate", ...)` for the
pure formatter utilities instead.

---

## 7. Consumer Wiring — Slot Time Display

**File:** `apps/web/__tests__/settings/display-format-consumers.test.ts`

Tests for the utility functions or component logic that reads display preferences and
formats time/distance strings throughout the app. Test the pure formatters, not the
full SlotCard component (which has its own test file).

```typescript
import { describe, it, expect } from "vitest";
import {
  formatTime,
  formatDistance,
  formatTemperature,
} from "@/lib/display-format";
```

### Tests

**formatTime**

- `formats "09:00" as "9:00 AM" when timeFormat is "12h"`
- `formats "13:30" as "1:30 PM" when timeFormat is "12h"`
- `formats "00:00" as "12:00 AM" when timeFormat is "12h"`
- `formats "12:00" as "12:00 PM" when timeFormat is "12h"`
- `formats "09:00" as "09:00" when timeFormat is "24h"`
- `formats "13:30" as "13:30" when timeFormat is "24h"`
- `returns empty string or null when input is null`

**formatDistance**

- `formats 1.6 km as "1.0 mi" when distanceUnit is "mi"` (1.6 km = 1.0 mi)
- `formats 1.6 km as "1.6 km" when distanceUnit is "km"`
- `handles 0 correctly for both units`

**formatTemperature**

- `formats 100 F as "37.8C" when temperatureUnit is "C"` (verify rounding)
- `formats 100 F as "100F" when temperatureUnit is "F"`
- `formats 0 C as "32F" when temperatureUnit is "F"`

---

## 8. Preferences API Enhancements

**Extend:** `apps/web/__tests__/api/settings-preferences.test.ts`

**Update `PREF_SELECT` assertion** in the existing "field whitelisting" test that checks the
`select` shape — add the new fields:
```typescript
expect(upsertCall.select).toEqual({
  dietary: true,
  mobility: true,
  languages: true,
  travelFrequency: true,
  // New fields:
  distanceUnit: true,
  temperatureUnit: true,
  dateFormat: true,
  timeFormat: true,
  theme: true,
  vibePreferences: true,
  travelStyleNote: true,
});
```

**Update "returns defaults when no record exists" test** — add new fields to expected default:
```typescript
expect(json).toEqual({
  dietary: [],
  mobility: [],
  languages: [],
  travelFrequency: null,
  // New display prefs (from DB defaults)
  distanceUnit: "mi",
  temperatureUnit: "F",
  dateFormat: "MM/DD/YYYY",
  timeFormat: "12h",
  theme: "system",
  // New travel interests
  vibePreferences: [],
  travelStyleNote: null,
});
```

**New describe blocks:**

```
describe("PATCH /api/settings/preferences — display preferences validation", () => {
```

- `accepts distanceUnit: "km" and upserts`
  - `await PATCH(makePatchRequest({ distanceUnit: "km" }))`
  - `expect(upsertCall.update).toEqual({ distanceUnit: "km" })`

- `returns 400 for distanceUnit: "miles" (not in enum)`

- `accepts temperatureUnit: "C"`

- `returns 400 for temperatureUnit: "celsius"`

- `accepts dateFormat: "DD/MM/YYYY"`

- `accepts dateFormat: "YYYY-MM-DD"`

- `returns 400 for dateFormat: "d/m/y"`

- `accepts timeFormat: "24h"`

- `returns 400 for timeFormat: "military"`

- `accepts theme: "dark"`

- `accepts theme: "system"`

- `returns 400 for theme: "auto"`

```
describe("PATCH /api/settings/preferences — vibePreferences validation", () => {
```

- `accepts valid vibePreferences array with known slugs`
  - `await PATCH(makePatchRequest({ vibePreferences: ["street-food", "hidden-gem"] }))`
  - `expect(upsertCall.update.vibePreferences).toEqual(["street-food", "hidden-gem"])`

- `returns 400 for vibePreferences array containing unknown slug`
  - `await PATCH(makePatchRequest({ vibePreferences: ["not-a-real-tag"] }))`
  - `expect(res.status).toBe(400)`

- `returns 400 for vibePreferences containing activity-level tag "cash-only" (not in user allowlist)`
  - `await PATCH(makePatchRequest({ vibePreferences: ["cash-only"] }))`
  - `expect(res.status).toBe(400)`

- `deduplicates vibePreferences array before saving`
  - `await PATCH(makePatchRequest({ vibePreferences: ["street-food", "street-food", "hidden-gem"] }))`
  - `expect(upsertCall.update.vibePreferences).toEqual(["street-food", "hidden-gem"])`
  - Same for `create` block

- `accepts empty vibePreferences array (clearing all tags)`
  - `await PATCH(makePatchRequest({ vibePreferences: [] }))`
  - `expect(upsertCall.update.vibePreferences).toEqual([])`

- `accepts all 23 valid tags`
  - Build an array with all 23 slugs; assert 200 + deduplicated array saved correctly

```
describe("PATCH /api/settings/preferences — travelStyleNote validation", () => {
```

- `accepts travelStyleNote string up to 500 chars`
  - `await PATCH(makePatchRequest({ travelStyleNote: "a".repeat(500) }))`
  - `expect(res.status).toBe(200)`

- `returns 400 for travelStyleNote exceeding 500 chars`
  - `await PATCH(makePatchRequest({ travelStyleNote: "a".repeat(501) }))`
  - `expect(res.status).toBe(400)`

- `accepts travelStyleNote: null (clearing the note)`

- `accepts travelStyleNote: undefined (field omitted, no change)`

- `does NOT call LLM on save (no external API calls happen in PATCH handler)`
  - Assert no `fetch` or Anthropic SDK calls were made (this guards against accidental
    LLM invocation being added to the save path)
  - `expect(global.fetch).not.toHaveBeenCalled()` (if fetch is the transport)

---

## 9. SettingsPage Mock Updates

**Extend:** `apps/web/__tests__/settings/SettingsPage.test.tsx`

Add two new vi.mock calls alongside the existing component mocks:

```typescript
vi.mock("@/components/settings/DisplayPreferences", () => ({
  DisplayPreferences: () => <section><h2>Display Preferences</h2></section>,
}));

vi.mock("@/components/settings/TravelInterests", () => ({
  TravelInterests: () => <section><h2>Travel Interests</h2></section>,
}));
```

**Update existing "renders all stub sections" test:**
```typescript
it("renders all stub sections including new V2 sections", () => {
  render(<SettingsPage />);
  expect(screen.getByText("My Preferences")).toBeInTheDocument();
  expect(screen.getByText("Display Preferences")).toBeInTheDocument(); // new
  expect(screen.getByText("Travel Interests")).toBeInTheDocument();    // new
  expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument();
  expect(screen.getByText("Privacy & Data")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "About" })).toBeInTheDocument();
});
```

**New section order test:**

- `sections render in correct order: Account → Subscription → Display Preferences → My Preferences → Travel Interests → Notifications → Privacy & Data → About`
  - `const headings = screen.getAllByRole("heading", { level: 2 }).map(h => h.textContent)`
  - Assert the array contains the section names in the correct order using `indexOf` comparisons:
    ```typescript
    const display = headings.indexOf("Display Preferences");
    const prefs = headings.indexOf("My Preferences");
    const interests = headings.indexOf("Travel Interests");
    expect(display).toBeLessThan(prefs);
    expect(prefs).toBeLessThan(interests);
    ```

**New billing portal UI test:**

```
describe("SettingsPage — SubscriptionBadge billing portal button", () => {
```

- `"Manage billing" button is not visible (fetch-on-click, never pre-rendered conditionally)`
  - Per the review notes: button always renders for non-free users, Stripe check is
    server-side on click. Assert the button is in the DOM for the beta session fixture.
  - `expect(screen.getByRole("button", { name: /manage billing/i })).toBeInTheDocument()`

- `clicking "Manage billing" POSTs to /api/settings/billing-portal`
  - Mock `global.fetch` to return `{ ok: true, json: async () => ({ url: "https://billing.stripe.com/test" }) }`
  - Mock `window.location.href = ""` (or spy on `window.location.assign`)
  - Click button → assert `global.fetch` called with `"/api/settings/billing-portal"` and `method: "POST"`

- `clicking "Manage billing" redirects to returned Stripe URL`
  - After fetch resolves: assert `window.location.href` equals `"https://billing.stripe.com/test"`
  - Use: `Object.defineProperty(window, "location", { writable: true, value: { href: "" } })`

- `clicking "Manage billing" shows error state when API returns 404 (no stripeCustomerId)`
  - `global.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 404, json: async () => ({ error: "No billing account" }) })`
  - Click button → `await waitFor(() => expect(screen.getByText(/no billing/i)).toBeInTheDocument())`

- `clicking "Manage billing" shows error state when API returns 500 (Stripe error)`
  - `global.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 500 })`
  - Assert generic error message renders, no redirect occurs

---

## Debounce / Timing Patterns — Reference

All debounce tests follow the pattern established in `PreferencesSection.test.tsx`.

```typescript
// Setup
vi.useFakeTimers(); // in beforeEach or renderAndLoad helper

// Trigger user interaction
await act(async () => { fireEvent.click(chip); });

// Advance timer in act wrapper (MANDATORY — prevents "act" warnings)
await act(async () => { await vi.advanceTimersByTimeAsync(499); });
expect(fetchMock).toHaveBeenCalledTimes(1); // not yet

await act(async () => { await vi.advanceTimersByTimeAsync(1); }); // 500ms total
expect(fetchMock).toHaveBeenCalledTimes(2); // fired

// Teardown
afterEach(() => { vi.useRealTimers(); });
```

For **blur-based saves** (textarea), use `userEvent.tab()` not `fireEvent.blur()` —
`userEvent.tab()` triggers the full browser blur sequence including any blur handlers.

For **immediate saves** (DisplayPreferences radio, notification toggles), omit timers:
```typescript
const user = userEvent.setup(); // no fakeTimers needed
await user.click(radio);
await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
```

---

## Accessibility Assertions — Reference

| Element | Assertion pattern |
|---|---|
| Toggle switch (on) | `expect(el).toHaveAttribute("aria-checked", "true")` |
| Toggle switch (off) | `expect(el).toHaveAttribute("aria-checked", "false")` |
| Radio pill (selected) | `expect(el).toHaveAttribute("aria-checked", "true")` |
| Radio pill (unselected) | `expect(el).toHaveAttribute("aria-checked", "false")` |
| Chip (active) | `expect(el).toHaveAttribute("aria-pressed", "true")` |
| Chip (inactive) | `expect(el).toHaveAttribute("aria-pressed", "false")` |
| Query by role | `screen.getByRole("switch")`, `screen.getByRole("radio")`, `screen.getByRole("button")` |
| Query by label | `screen.getByRole("switch", { name: /check-in prompts/i })` for specific toggle |

**Note on radio pills vs HTML `<input type="radio">`:** The design system uses styled
`<button role="radio">` pills (not native inputs) based on the existing Preferences
and Notifications patterns. Use `getByRole("radio")` regardless of underlying element.
If the component uses native `<input type="radio">`, the `aria-checked` attribute is not
needed (use `.checked` property instead). Confirm during implementation.

---

## Edge Cases Matrix

| Scenario | File | Key assertion |
|---|---|---|
| All 23 vibe tags selected | TravelInterests | PATCH body has 23 slugs, all valid |
| travelStyleNote = 500 chars (boundary) | preferences API | 200, saved |
| travelStyleNote = 501 chars | preferences API | 400 |
| preTripDaysBefore = 2 (invalid) | notifications API | 400 |
| theme = "auto" (invalid) | preferences API | 400 |
| stripeCustomerId = null (beta user) | billing-portal API | 404 |
| Stripe API throws | billing-portal API | 500, no Stripe internals in response |
| checkinReminder = false (explicit) | notifications API | saved, not treated as absent |
| Cookie absent, layout reads theme | theme-cookie | defaults to "system" |
| Cookie = "theme=blue" (injected) | theme-cookie | sanitized to "system" |
| Textarea blur without typing | TravelInterests | no PATCH fired |
| vibePreferences with activity-level tag | preferences API | 400 |
| Duplicate vibe slugs | preferences API | deduplicated before save |
| PATCH body with userId field | both APIs | userId from session only |

---

## Test Count Summary

| File | New tests | Updates to existing |
|---|---|---|
| DisplayPreferences.test.tsx | ~22 | — |
| TravelInterests.test.tsx | ~20 | — |
| settings-billing-portal.test.ts | ~10 | — |
| settings-notifications.test.ts | ~12 | 3 (DEFAULTS, field count, upsert shape) |
| NotificationsSection.test.tsx | ~12 | 2 (toggle count, DEFAULTS) |
| theme-cookie.test.ts | ~8 | — |
| ics-export.test.ts | ~7 | — |
| display-format-consumers.test.ts | ~12 | — |
| settings-preferences.test.ts | ~18 | 2 (defaults shape, PREF_SELECT) |
| SettingsPage.test.tsx | ~6 | 2 (mock list, stub sections assertion) |

**Total new tests: ~127. Updates to existing: ~9.**

Running count if all pass: ~397 + 127 = ~524 tests project-wide.
