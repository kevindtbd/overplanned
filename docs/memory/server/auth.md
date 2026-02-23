# Server / Auth

## Stack
- NextAuth.js with Google OAuth only
- DB sessions (NOT JWT), max 30d / 7d idle
- `@auth/prisma-adapter` — expects `image` on User (adapter writes `image`, app reads `avatarUrl`)

## Key Files
- `lib/auth/config.ts` — NextAuth config
- `lib/auth/session.ts` — Session helpers
- `lib/auth/gates.ts` — RBAC gates, `getEffectiveTier`, FEATURE_GATES
- `app/api/auth/[...nextauth]/route.ts` — NextAuth route
- `app/api/auth/dev-login/route.ts` — Dev login bypass

## Access Control
- Roles: 'beta' | 'lifetime' | 'free' | 'pro'
- All new signups default to role = 'beta'
- Lifetime users set via SQL — never hit paywall
- Access check: `['beta', 'lifetime', 'pro'].includes(user.role)`
- Stripe wired but NOT enforcing payment (beta mode)

## Known Issues
- `@/lib/auth` barrel import doesn't exist — use individual file imports
- NextAuth redirect validation added in feature units sprint

## Learnings
- (space for future compound learnings)
