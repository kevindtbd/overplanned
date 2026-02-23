# UI / Landing Page

## Components
- `GlobeCanvas.tsx` — Three.js globe, `next/dynamic({ ssr: false })`, viewport intersection trigger, skip on mobile (<900px)
- `TripMapCanvas.tsx` — Trip visualization canvas
- `ItineraryCard.tsx` — Sample itinerary preview card
- `LandingNav.tsx` — Landing page navigation
- `WaitlistForm.tsx` — Email capture form
- `RevealOnScroll.tsx` — Scroll-triggered animations

## Design Rules
- No ML sauce on landing page — never reveal behavioral signals or data pipeline specifics
- "Creepy" threshold — frame features as utility, not surveillance
- Only positive features for group trips — no conflict detection framing
- Decorative viz > informational viz
- Globe canvas: intersection observer trigger, skip on mobile

## Learnings
- (space for future compound learnings)
