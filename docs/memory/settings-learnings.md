# Settings Page Learnings

## Brainstorm: Settings V2 (2026-02-22)

### Cross-referencing docs surfaces real gaps
- The doc exploration agent found `checkin_reminder` and `pre_trip_days_before` defined in the product ML features doc but missing from the Prisma schema and UI. Without cross-referencing, these would have stayed invisible.
- The search specialist found display format preferences (units, date/time) are table stakes for travel apps — conspicuously absent when .ics export and slot times already ship in non-US-friendly formats.

### Philosophy docs are design constraints, not just vibes
- Travel Profile stub was killed because the philosophy doc explicitly says "don't tell users what you think they are." This isn't a preference — it's a locked design principle. Any future feature that exposes ML persona data directly to users violates it.
- The "invisible intelligence" principle means: intelligence shows up in recommendation quality, never in dashboard displays.

### Stubs should have a reason to exist before they're created
- TravelProfileStub existed from day 1 but had no clear purpose that wasn't already covered by Preferences. Creating stubs without a design doc leads to "we have this section but why" situations.

### Hybrid input > pure structured OR pure free-form
- 16 checkboxes captured constraints (what you can't eat, what access you need) but zero signal about what kind of traveler you ARE
- Pure free-form is too open for a settings page (feels weird, high cognitive load)
- Hybrid: curated vibe tags from existing vocabulary (23 user-relevant tags) + optional "anything else" textarea. Tags plug directly into ranking engine, free-form feeds ML async.

### Stripe billing: don't abstract for payment providers you don't use
- Apple IAP only matters when a native iOS app exists. Overplanned is a web app. Ship Stripe-only, don't build `paymentProvider` enums.

### Dark mode toggle needs flash-prevention
- Design system already has full dark mode tokens (`data-theme="dark"`)
- But naive implementation (load page → fetch theme from DB → apply) causes flash-of-wrong-theme
- Solution: inline script in root layout reads theme cookie, applies `data-theme` before first paint. Cookie set client-side alongside DB save.

### Settings sections that don't connect to product features are theater
- Currency display, language, emergency contacts, home airport — these feel like "a real travel app should have these" but nothing in the product consumes them today
- Rule: only ship settings when the product surface that reads them exists
