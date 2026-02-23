# UI / Trip Views

## Components
- `DayView.tsx` — Timeline display, slot cards, day navigation
- `DayNavigation.tsx` — Day selector
- `RevealAnimation.tsx` — Itinerary reveal after generation
- `WelcomeCard.tsx` — Post-creation welcome/progress nudge
- `PackingList.tsx` — Packing list display
- `TripSettings.tsx` — Per-trip settings
- `LegEditor.tsx` — Multi-city leg management
- `LegEditorRow.tsx` — Individual leg row
- `CityCombobox.tsx` — City search/select

## Pages
- `app/trip/[id]/page.tsx` — Trip detail
- `app/trip/[id]/calendar/page.tsx` + `CalendarClient.tsx` — Calendar view
- `app/trip/[id]/map/page.tsx` — Map view
- `app/trip/[id]/reflection/page.tsx` — Post-trip reflection
- `app/trips/[id]/generating/page.tsx` — Generation loading screen

## Multi-City (TripLeg)
- Trip -> TripLeg[] (ordered by position, max 8 legs)
- dayNumber is leg-relative, absolute day computed at read time
- GET /api/trips returns derived: primaryCity, primaryCountry, primaryDestination, legCount
- Trip detail derives city/destination/timezone from legs[0]

## Learnings
- (space for future compound learnings)
