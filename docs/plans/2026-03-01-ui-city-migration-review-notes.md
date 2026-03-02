# UI City Migration — Deepen Plan Review Notes

**Date**: 2026-03-01

## Critical Issues Found

### 1. Portland Duplicate Key Bug (MUST FIX)
**Problem**: Both Portland, OR and Portland, ME have `city.city === "Portland"`. CityCombobox and DestinationStep use `key={city.city}` — React duplicate key warning + broken rendering.
**Fix**: Use `slug` as identity everywhere. Switch `key={city.slug}`, `aria-selected` checks to slug-based.

### 2. Country Search Filter Useless at Scale
**Problem**: 28 of 30 cities are "United States". Typing "United" matches 28 results.
**Fix**: Search on `city` + `state` + `destination` fields. Drop `country` from filter.

## Gaps Clarified

### Type Contract
- New type is a **strict superset** of existing `CityData` — add `slug`, `state`, `lat`, `lng` fields.
- Keep the type name as `CityData` for backward compatibility.
- Export from `lib/cities.ts` as the single source.

### UX Copy Updates
- DestinationStep "select a launch city" → update to reflect broader city selection
- Empty state "No matching launch city" → guide users toward freeform resolver

## Risks Confirmed
- `lib/cities.ts` must be isomorphic (no `"server-only"`) — used by client components
- Globe stays untouched (decorative)
- Test fixtures stay untouched (separate concern)

## No Issues Found With
- Data shape (slug, city, state, country, timezone, destination, lat, lng)
- File scope (8 files)
- Featured city selection (Bend, Austin, Seattle)
- Unsplash photo approach (fallback URL exists)
