# Server / Settings API

## Routes
- `app/api/settings/preferences/route.ts` — User preferences CRUD
- `app/api/settings/notifications/route.ts` — Notification preferences CRUD
- `app/api/settings/display/route.ts` — Display preferences (theme, units, date format)
- `app/api/settings/privacy/route.ts` — Privacy settings
- `app/api/settings/account/route.ts` — Account info
- `app/api/settings/billing-portal/route.ts` — Stripe billing portal redirect
- `app/api/settings/export/route.ts` — GDPR data export

## Key Libraries
- `lib/validations/settings.ts` — Settings Zod schemas
- `lib/stripe.ts` — Stripe client

## Patterns
- Field whitelisting via Zod — reject unknown fields
- GDPR: data export endpoint, privacy controls
- Stripe billing portal: redirect-based, not embedded

## Learnings
- (space for future compound learnings)
