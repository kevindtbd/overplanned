# Server / Billing

## Routes
- `app/api/settings/billing-portal/route.ts` — Stripe billing portal redirect

## Key Libraries
- `lib/stripe.ts` — Stripe client initialization

## Current State (Beta)
- Stripe is wired but NOT gating anyone
- No paywalls until explicitly instructed
- Billing portal redirect works but no active subscriptions
- Don't abstract for payment providers you don't use (no Apple IAP until native app)

## Learnings
- (space for future compound learnings)
