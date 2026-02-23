# UI / Settings

## Components
- `AccountSection.tsx` — Account info display
- `AboutSection.tsx` — App info
- `PreferencesSection.tsx` — User preferences
- `PrivacySection.tsx` — Privacy controls
- `NotificationsSection.tsx` — Notification preferences
- `DisplayPreferences.tsx` — Theme, units, date/time format
- `SubscriptionBadge.tsx` — Tier badge display
- `TravelInterests.tsx` — Vibe tag selection + free-form textarea

## Page
- `app/settings/page.tsx` — Settings page (all sections)

## Design Principles
- Only ship settings when the product surface that reads them exists
- Hybrid input > pure structured OR pure free-form
- 23 curated vibe tags from existing vocabulary + optional textarea
- Dark mode toggle needs flash-prevention (cookie + inline script)
- Stripe billing: Stripe-only, no multi-provider abstraction
- "Invisible intelligence" — never expose ML persona data to users

## Learnings
- Cross-referencing docs surfaces real gaps (e.g., checkin_reminder in ML doc but missing from schema)
- Philosophy docs are design constraints — "don't tell users what you think they are" killed Travel Profile stub
- Stubs without design docs lead to "why does this exist" situations
- Settings sections that don't connect to product features are theater
