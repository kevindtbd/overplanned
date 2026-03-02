# UI City Migration: Hardcoded to Seeded Cities

**Date**: 2026-03-01
**Status**: Final (post-deepen + architect/security/test review)

## Problem

The UI has 13 hardcoded "launch cities" (Tokyo, Kyoto, Barcelona, New York, etc.) but the actual seeded pipeline data covers 30 different cities — mostly US outdoor/adventure towns. Almost zero overlap. Users selecting cities in the UI can't pick destinations that have real data.

## Decision

Replace all hardcoded city data in the frontend with the 30 cities that have been actively seeded (have `data/seed_progress/*.json` files). Tokyo excluded — it has a seed_progress file but no city_configs.py entry (orphan experiment).

## The 30 Seeded Cities

Asheville (NC), Austin (TX), Bend (OR), Bozeman (MT), Burlington (VT), Columbus (OH), Denver (CO), Detroit (MI), Durango (CO), Durham (NC), Flagstaff (AZ), Fort Collins (CO), Hood River (OR), Jackson Hole (WY), Madison (WI), Mammoth Lakes (CA), Mexico City (Mexico), Missoula (MT), Moab (UT), Nashville (TN), New Orleans (LA), Portland (OR), Portland (ME), Seattle (WA), Sedona (AZ), Tacoma (WA), Taos (NM), Telluride (CO), Truckee (CA), Tucson (AZ)

## Data Shape

```ts
export interface CityData {
  slug: string;        // "bend" — matches seed_progress filenames, UNIQUE identity key
  city: string;        // "Bend"
  state: string;       // "OR" (empty string for international)
  country: string;     // "United States"
  timezone: string;    // "America/Los_Angeles"
  destination: string; // "Bend, OR" (or "Mexico City, Mexico" for intl)
  lat: number;         // 44.06
  lng: number;         // -121.31
}
```

Type name stays `CityData` (superset of existing type — zero breakage for consumers that only use city/country/timezone/destination).

## Files Changed (10 production + 4 test files)

### 1. `lib/cities.ts` (NEW)
- Canonical `LAUNCH_CITIES` array with 30 entries
- `CityData` type export (superset of existing shape)
- Helpers: `findCity(slug)`, `getCityByName(name)` — `getCityByName` is exact-match only, returns first match for ambiguous names (Portland → OR)
- Must be isomorphic (NO `"server-only"`) — used by client components
- JSDoc on slug: closed vocabulary, any route accepting slug as URL param must validate against this list

### 2. `lib/city-resolver.ts`
- Delete inline `LAUNCH_CITIES` (lines 7-21)
- Import `LAUNCH_CITIES` from `lib/cities.ts`
- `resolveCity()` fast-path checks against new list
- Keeps `"server-only"` — only the resolver is server-only, not the city data
- Note: resolver returns `ResolvedCity` (4 fields), NOT `CityData` (8 fields). This is correct — LLM-resolved cities don't have slug/state/lat/lng.

### 3. `components/trip/CityCombobox.tsx`
- Delete inline `LAUNCH_CITIES` + `CityData` type
- Import both from `lib/cities.ts`
- **CRITICAL**: Change `key={city.city}` to `key={city.slug}` (Portland duplicate key bug)
- **CRITICAL**: Change `aria-selected` and all equality checks from `city.city` to `city.slug`
- **Search filter**: change from `city + country` to `city + state + destination`
- Display: show state abbreviation instead of country in dropdown items
- Freeform resolve response typing: `CityData` → accept partial (resolver returns 4 fields, not 8)

### 4. `app/onboarding/components/DestinationStep.tsx`
- Delete inline `LAUNCH_CITIES` + `LaunchCity` type
- Import from `lib/cities.ts`
- **CRITICAL**: Same slug-based identity fixes as CityCombobox
- **Copy update**: "select a launch city" → "pick a city"
- **Empty state copy**: "No matching launch city..." → "Not in our list? Type any city name."

### 5. `app/onboarding/page.tsx` (MISSED IN V1 — caught by architect review)
- Change import from `DestinationStep` to `lib/cities.ts` for LAUNCH_CITIES + type
- 3 lookup sites: city prefill, draft resume, goBack()
- **Freeform sentinel**: `goBack()` constructs `CityData` without slug/state/lat/lng. Use sentinel: `{ slug: "", state: "", lat: 0, lng: 0, ...existingFields }`

### 6. `lib/city-photos.ts`
- Replace 15 international city photo URLs with 30 seeded city photo URLs
- Key by `slug` not `city` name (resolves Portland ambiguity — `portland` and `portland-me` get separate photos)
- `getCityPhoto` signature: accept slug OR city name, check slug first
- Fallback URL stays

### 7. `components/dashboard/QuickStartGrid.tsx`
- `FEATURED_CITY_NAMES`: `["Bend", "Austin", "Seattle"]` (matched by slug: `["bend", "austin", "seattle"]`)
- Update import to use `lib/cities.ts` instead of DestinationStep

### 8. `app/discover/page.tsx`
- Default city: `"Bend"` (was `"Tokyo"`)

### 9. `app/page.tsx`
- Hero pills: `["Bend", "Austin", "Nashville", "Asheville"]`
- Waitlist copy: "First cities at launch: Bend, Austin, Seattle, Nashville, Asheville. iOS and Android."

### 10. `app/explore/ExploreClient.tsx` (caught by security review)
- Replace deprecated `source.unsplash.com` fallback with `getCityPhoto()` from `lib/city-photos.ts`

### Test Files

### T1. `__tests__/lib/cities.test.ts` (NEW)
- 30 cities, slug uniqueness, Portland duplicate contract, helper tests
- `getCityByName("Portland")` returns OR (first match), document ambiguity

### T2. `__tests__/trip/CityCombobox.test.tsx` (UPDATE)
- Replace Tokyo/Kyoto/Osaka assertions with seeded city names
- Change count from 13 → 30
- Replace country filter test with state filter test
- Add Portland duplicate-key render test
- Add Portland OR/ME select distinction test
- Update `onChange` shape assertion

### T3. `__tests__/dashboard/DashboardPage.test.tsx` (UPDATE)
- Replace Tokyo/New York/Mexico City assertions with Bend/Austin/Seattle
- Update link href assertions

### T4. `__tests__/onboarding/onboarding-draft.test.tsx` (UPDATE)
- Remove stale `LAUNCH_CITIES` export from DestinationStep mock

## NOT Changed

- **`GlobeCanvas.tsx`** — decorative, keeps international cities (user request)
- **`ItineraryCard.tsx`** — Kyoto demo data stays (decorative)
- **`__tests__/fixtures/leg-factory.ts`** — TripLeg fixture, not constrained to launch city list
- **`admin/seed-viz/page.tsx`** — has its own local `CityData` interface (unrelated type, no LAUNCH_CITIES dependency)
- **Backend** — no changes, city_configs.py is already correct

## Risks & Mitigations

1. **`city-resolver.ts` has `"server-only"`** — `lib/cities.ts` must NOT have `"server-only"`. Resolver imports city data but keeps its own server-only guard.
2. **Portland duplicate key** — FIXED by using `slug` as React key and identity. Two Portlands: `portland` (OR) and `portland-me` (ME).
3. **Portland photo ambiguity** — FIXED by keying photos on slug, not city name.
4. **Search filter at scale** — FIXED by searching city + state + destination instead of city + country.
5. **Type backward compat** — CityData is a superset. Old consumers using {city, country, timezone, destination} continue working. Freeform cities use sentinel values for new fields.
6. **Freeform city type gap** — CityCombobox types API response as `CityData` but resolver returns `ResolvedCity` (4 fields). Fix: accept partial or use `Partial<CityData> & ResolvedCity`.
7. **Rate limiter is instance-local** — pre-existing, not introduced by this migration. Acceptable for beta scale.
