# M-001: Onboarding Flow

## Description
Trip creation wizard: destination, dates, Trip DNA preferences, preset templates.

## Task
Create the onboarding flow at apps/web/app/onboarding/:

1. Fork screen: "Plan a trip" vs "Just exploring"
   - "Plan a trip" → full onboarding flow
   - "Just exploring" → discover feed (Track 3 M-008)

2. Trip creation steps:
   - Step 1: Destination city (autocomplete from 13 launch cities)
   - Step 2: Travel dates (date picker, start + end)
   - Step 3: Trip name (auto-generated suggestion + custom)
   - Step 4: Trip DNA — pace (packed/moderate/relaxed), morning preference (early/mid/late), food chips (select from vibe tags in dining category)
   - Step 5: Preset template selection (optional): "Foodie Weekend", "Culture Deep Dive", "Adventure", "Chill"

3. On completion:
   - Create Trip row: destination, startDate, endDate, name, timezone (auto-populate IANA format from city), status: planning
   - Create TripMember row: userId, tripId, role: organizer
   - Save personaSeed JSON on Trip: { pace, morningPreference, foodPreferences, template }
   - Navigate to generation loading screen

Design system: Sora headings, DM Mono labels, terracotta accent, warm tokens. No emoji. SVG icons only.

## Output
apps/web/app/onboarding/page.tsx

## Zone
onboarding

## Dependencies
none

## Priority
100

## Target Files
- apps/web/app/onboarding/page.tsx
- apps/web/app/onboarding/components/ForkScreen.tsx
- apps/web/app/onboarding/components/DestinationStep.tsx
- apps/web/app/onboarding/components/DatesStep.tsx
- apps/web/app/onboarding/components/TripDNAStep.tsx
- apps/web/app/onboarding/components/TemplateStep.tsx

## Files
- prisma/schema.prisma
- docs/overplanned-design-v4.html
- docs/plans/vertical-plans-v2.md
