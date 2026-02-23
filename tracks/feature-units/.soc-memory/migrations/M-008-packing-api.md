# M-008: Packing API Routes + PackingList Component

## Description
Track 5: Create packing generation + check endpoints, Zod schema, PackingList.tsx component, and tests.

## Task

### 1. Zod Schema (`apps/web/lib/validations/packing.ts`)
```typescript
import { z } from "zod";

export const packingGenerateSchema = z.object({
  regenerate: z.boolean().default(false),
}).optional();

export const packingCheckSchema = z.object({
  itemId: z.string().uuid(),
  checked: z.boolean(),
});

// Output validation for LLM response
export const packingItemSchema = z.object({
  id: z.string(),
  text: z.string().max(100),
  category: z.enum(["essentials", "clothing", "documents", "tech", "toiletries", "misc"]),
  checked: z.boolean().default(false),
});

export const packingListSchema = z.object({
  items: z.array(packingItemSchema).max(50),
});
```

### 2. POST /api/trips/[id]/packing/route.ts (auth required, joined member)
- Auth: session + membership (joined member)
- Validate trip status: planning or active -> 409 if not
- Parse optional body with `packingGenerateSchema`
- **If packingList exists AND regenerate !== true:** return existing list immediately
- **If generating:**
  - Rate limit: LLM tier (3 req/hour by userId)
  - **Input sanitization (V6):** Sanitize destination, template name, persona values before LLM prompt
  - Call Claude Haiku (`claude-haiku-4-5-20251001`) with structured prompt:
    - Inputs: destination, city, country, startDate, endDate, duration (days), presetTemplate, personaSeed
    - Request JSON output matching `packingListSchema`
    - Cap at 30 items
  - **Validate LLM output** with `packingListSchema.safeParse()` — if invalid, return error
  - Generate UUID for each item: `crypto.randomUUID()` (UUIDs for items are fine, only tokens need 256-bit)
  - Store in `Trip.packingList` as JSONB with `{ items, generatedAt, model }`
- Return: `{ packingList }`

### 3. PATCH /api/trips/[id]/packing/route.ts (auth required, joined member)
- Auth: session + membership
- Parse body with `packingCheckSchema`
- Read current `packingList` -> 404 if null
- Find item by `itemId` in items array -> 404 if not found
- Update `checked` field on that item
- Write back to `Trip.packingList`
- Log BehavioralSignal: `packing_checked` or `packing_unchecked`
- Return: `{ packingList }`

### 4. PackingList Component (`apps/web/components/trip/PackingList.tsx`)
- Props: `{ tripId: string, packingList: PackingListData | null, isOrganizer: boolean }`
- If no packing list: show "Generate packing list" button
- If exists: show categorized checklist grouped by category
- Each item: checkbox + text, optimistic UI on toggle (PATCH immediately)
- "Regenerate" button (only organizer) with confirmation
- Progress: "12/18 packed" counter
- Design: follows Overplanned design system (Sora headings, DM Mono labels, warm tokens, no emoji)
- Only visible for planning/active trips

### 5. Tests (`apps/web/__tests__/api/packing.test.ts`)
- Auth: standard guards
- Generate: returns existing list without LLM call, regenerate clears checked states
- LLM: validates output schema, handles LLM errors gracefully, rate limiting
- Check: finds item by ID, toggles checked, logs correct signal
- Input sanitization: strips potentially harmful content from LLM prompt
- Target: 15-20 tests

## Output
apps/web/lib/validations/packing.ts
apps/web/app/api/trips/[id]/packing/route.ts
apps/web/components/trip/PackingList.tsx
apps/web/__tests__/api/packing.test.ts

## Zone
api

## Dependencies
M-002, M-003

## Priority
75

## Target Files
- apps/web/lib/validations/packing.ts
- apps/web/app/api/trips/[id]/packing/route.ts
- apps/web/components/trip/PackingList.tsx
- apps/web/__tests__/api/packing.test.ts

## Files
- docs/plans/2026-02-22-feature-units-sprint.md (Track 5 spec)
- docs/plans/2026-02-22-feature-units-review-notes.md (V6 sanitization, regeneration)
- apps/web/app/api/trips/[id]/route.ts (auth pattern reference)
- docs/overplanned-design-v4.html (design system reference)
