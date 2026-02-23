# Settings Page — Implementation Design
*2026-02-22 | Brainstorm + Deepen + Agent Review*

## Scope Decision
- **Minimal**: build e2e where DB supports it, scaffold schema for the rest
- **Real sections**: Account (name edit, email display, OAuth provider, sign out), About/Legal (static)
- **Scaffolded sections**: Subscription (tier badge only), Travel Profile (cold-start stub), My Preferences (schema + placeholder), Notifications (schema + placeholder), Privacy & Data (consent schema + placeholder)

## Nav Entry Point
- **Desktop**: ProfileIcon as Link in DesktopSidebar footer (alongside existing Beta badge)
- **Mobile**: Wire existing MobileTopBar avatar placeholder (AppShell line 62) as Link to `/settings`. Remove `aria-hidden`, add accessible label.
- Do NOT modify MobileNav bottom bar (stays at 2 items)

## Page Layout
- Single scrollable page, no tabs
- `"use client"` page matching dashboard pattern (`useSession()` + `fetch()`)
- Wrapped in `<AppShell>` like dashboard
- Client sections separated by `border-b border-warm-border`
- Warm-surface cards for grouped fields
- Mobile-first, single column
- Loading skeleton + error state (matching dashboard pattern with CardSkeleton/ErrorState)

## File Structure
```
components/settings/               <- follows components/<domain>/ convention
  AccountSection.tsx               <- REAL: name edit, email, OAuth, sign out
  SubscriptionBadge.tsx            <- STUB: tier badge
  TravelProfileStub.tsx            <- STUB: cold-start message
  PreferencesStub.tsx              <- STUB: placeholder
  NotificationsStub.tsx            <- STUB: placeholder
  PrivacyStub.tsx                  <- STUB: placeholder
  AboutSection.tsx                 <- REAL: version, legal links, feedback

app/settings/
  page.tsx                         <- "use client" page component

app/api/settings/
  account/route.ts                 <- PATCH: update display name
```

## API Routes
- `PATCH /api/settings/account` — update display name only
- No other API routes until sections go live
- No DELETE route (account deletion deferred — no stub endpoints without UI consumers)

### PATCH /api/settings/account — Spec
- Auth: `getServerSession(authOptions)`, 401 if no session
- userId derived from `session.user.id` ONLY — never from request body
- **Whitelist**: only `name` field is writable. All other fields in body are ignored.
- Validation (Zod):
  - `name`: string, trim, min 1 char, max 100 chars, strip control characters
  - Reject empty/whitespace-only strings
- Returns: `{ name: string }` (updated value only, no sensitive fields)
- `router.refresh()` on client after success to update session

## Schema Additions (Prisma)

All 3 models include User relation with `onDelete: Cascade`. User model gets corresponding optional relation fields.

### UserPreference
```prisma
model UserPreference {
  id              String   @id @default(uuid())
  userId          String   @unique
  user            User     @relation(fields: [userId], references: [id], onDelete: Cascade)
  dietary         String[] // validated: vegan, vegetarian, halal, kosher, gluten-free, nut-allergy, shellfish
  mobility        String[] // validated: wheelchair, low-step, elevator-required, sensory-friendly
  languages       String[] // validated: non-english-menus, limited-english-staff
  travelFrequency String?  // validated: few-times-year | monthly | constantly
  createdAt       DateTime @default(now())
  updatedAt       DateTime @updatedAt
}
```

### NotificationPreference
```prisma
model NotificationPreference {
  id                String  @id @default(uuid())
  userId            String  @unique
  user              User    @relation(fields: [userId], references: [id], onDelete: Cascade)
  tripReminders     Boolean @default(true)
  morningBriefing   Boolean @default(true)
  groupActivity     Boolean @default(true)
  postTripPrompt    Boolean @default(true)
  citySeeded        Boolean @default(true)
  inspirationNudges Boolean @default(false)
  productUpdates    Boolean @default(false)
  createdAt         DateTime @default(now())
  updatedAt         DateTime @updatedAt
}
```

### DataConsent
```prisma
model DataConsent {
  id                  String  @id @default(uuid())
  userId              String  @unique
  user                User    @relation(fields: [userId], references: [id], onDelete: Cascade)
  modelTraining       Boolean @default(false)  // opt-in, not opt-out (GDPR)
  anonymizedResearch  Boolean @default(false)  // opt-in, not opt-out (GDPR)
  createdAt           DateTime @default(now())
  updatedAt           DateTime @updatedAt
}
```

### User model additions
```prisma
// Add to User model:
  userPreference          UserPreference?
  notificationPreference  NotificationPreference?
  dataConsent             DataConsent?
```

## Account Section (Real Implementation)
- **Display name**: inline edit field, PATCH on blur/enter, optimistic UI with revert on failure
- **Email**: read-only (Google OAuth), shows email from session
- **Connected accounts**: shows "Google" badge (derived from session — user signed in via Google OAuth, so always Google)
- **Sign out**: calls `signOut()` from next-auth/react, with `callbackUrl: "/"`
- **No delete account button** in v1

## Stub Sections
Each stub section renders:
- Section heading (font-sora, text-ink-100)
- Warm-surface card with 1-2 lines of context
- No "coming soon" badges — natural language only

Stub copy:
- **Subscription**: Shows current tier badge (beta/pro/lifetime from session). "Your plan details will appear here."
- **Travel Profile**: "Your travel profile builds as you explore. Check back after your first trip."
- **Preferences**: "Set dietary needs, accessibility requirements, and travel pace. Available soon."
- **Notifications**: "Control how Overplanned reaches you. Available soon."
- **Privacy**: "Manage your data, download exports, and control how your signals are used. Available soon."

## Validation Schemas (Zod)
```typescript
// lib/validations/settings.ts
const updateAccountSchema = z.object({
  name: z.string().trim().min(1).max(100),
});
```

Future schemas for preferences/notifications will validate arrays against allowlists with max length caps.

## Design System Compliance
- Fonts: Sora headings, DM Mono labels
- Colors: warm-background page bg, warm-surface cards, warm-border dividers
- Accent: terracotta for CTAs and active states
- Icons: inline SVG only, matching existing nav icon pattern (18-20px, stroke 1.8)
- No emoji anywhere

## Open Items (Future)
- Account deletion cascade logic (privacy spec in admin-tooling.md)
- Persona rendering endpoint (depends on ML pipeline)
- Data export async job (depends on backend infrastructure)
- Stripe billing portal integration (depends on Stripe activation)
- Home city field — deferred to v2 per spec
- "Sign out all devices" — infrastructure exists (revokeAllUserSessions), expose in future
- Audit logging for consent changes when consent section goes live
- GDPR special category consent for dietary/mobility data
