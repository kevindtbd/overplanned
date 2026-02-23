# Product / Access Control

## Roles
- 'beta' | 'lifetime' | 'free' | 'pro'
- All new signups: role = 'beta'
- Lifetime: set via SQL, never hit paywall
- Access check: `['beta', 'lifetime', 'pro'].includes(user.role)`

## Beta Mode
- Stripe wired but NOT enforcing payment
- No paywalls until explicitly instructed
- All beta users have full access

## Feature Gates
- `getEffectiveTier` in `lib/auth/gates.ts`
- FEATURE_GATES configuration
- Feature flag overrides per user (admin-managed)

## Learnings
- (space for future compound learnings)
