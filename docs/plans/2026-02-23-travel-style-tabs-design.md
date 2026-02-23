# Travel Style Tabbed Section — Design

## Problem
PreferencesSection (8 fieldsets + textarea, ~46 interactive elements) and TravelInterests (23 vibe tags + textarea, ~24 elements) stack into ~70 chips on mobile. It's a wall of slop.

## Solution
Merge both into a single **TravelStyleSection** component with 2 horizontal tabs:
- **Practical** — dietary, accessibility, budget, spending, accommodation, transit, languages, frequency + preferencesNote textarea
- **Vibes** — 5 vibe groups (23 tags) + travelStyleNote textarea

Each tab is manageable on mobile (max 8 groups + textarea). Tab bar inside the card, terracotta underline on active.

## Tab Bar Styling
```
font-dm-mono text-xs uppercase tracking-wider
Active: text-accent border-b-2 border-accent
Inactive: text-ink-400 hover:text-ink-300
gap-4, pb-3, border-b border-warm-border
```

## Practical Tab Layout
Within the tab: `grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4`
1. Dietary needs (10 chips)
2. Accessibility (6 chips)
3. Budget comfort (4 radio + null)
4. Spending priorities (4 chips)
5. Accommodation (5 chips)
6. Getting around (6 chips)
7. Language comfort (2 chips)
8. Travel frequency (3 radio + null)
9. Textarea (sm:col-span-2): "Anything else about how you prefer to travel?"

## Vibes Tab Layout
Vertical stack, dividers between groups:
1. Pace & Energy (3 tags)
2. Discovery Style (4 tags)
3. Food & Drink (4 tags)
4. Activity Type (6 tags)
5. Social & Time (6 tags)
6. Textarea: "Anything else about how you travel?"

## File Changes
- **New**: `components/settings/TravelStyleSection.tsx` — merged component
- **Delete**: `components/settings/PreferencesSection.tsx`
- **Delete**: `components/settings/TravelInterests.tsx`
- **Update**: `app/settings/page.tsx` — swap imports, update SECTION_ANCHORS
- **New**: `__tests__/settings/TravelStyleSection.test.tsx` — merged tests
- **Delete**: `__tests__/settings/PreferencesSection.test.tsx`
- **Delete**: `__tests__/settings/TravelInterests.test.tsx`

## No Backend Changes
Same API, same schema, same validation. Purely UI restructure.

## Decisions
- 2 tabs not 3 — Notes tab was too thin, textareas live at bottom of each tab
- No accordion — tabs reduce the wall more effectively
- No wizard — overkill for settings page where users change one thing at a time
- Keep 2-col grid inside Practical tab on sm: breakpoint, single col on mobile
