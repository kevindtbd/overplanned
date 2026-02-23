# Settings Page Plan — Deepen Review Notes
*2026-02-22*

## Gaps Found & Resolutions

### Gap 1: FK Relations on New Models (CRITICAL)
- **Issue**: Plan said "no User relation yet" — orphan rows on user deletion
- **Resolution**: Add `userId` relation to User with `onDelete: Cascade` on all 3 new models (UserPreference, NotificationPreference, DataConsent). Costs nothing, prevents data integrity issues.

### Gap 2: Session Sync After Name Edit
- **Issue**: PATCH display name updates DB, but session object caches old name until refresh
- **Resolution**: Call `router.refresh()` after successful PATCH. Re-runs server component, picks up new name from DB via session callback.

### Gap 3: Mobile Entry Point Wrong
- **Issue**: Plan said "add ProfileIcon to MobileNav bottom bar" — but MobileNav has 2 items with `justify-around`, adding a 3rd changes spacing. AppShell's MobileTopBar already has a placeholder avatar circle (line 62).
- **Resolution**: Wire the existing MobileTopBar avatar circle as a Link to `/settings`. No MobileNav changes. Desktop sidebar gets ProfileIcon in footer.

### Gap 4: Delete Account Stub Is Worse Than Nothing
- **Issue**: Plan described a "type DELETE to confirm" modal that doesn't actually delete anything. Showing destructive UX that does nothing erodes trust.
- **Resolution**: Skip delete account button entirely in v1. Add when cascade pipeline exists.

### Gap 5: Data Fetching Pattern Mismatch
- **Issue**: Plan described page.tsx as a "server component" — but the established pattern (dashboard, trip detail) is `"use client"` + `useEffect` + `fetch()`. Introducing a server component pattern for one page creates inconsistency.
- **Resolution**: Follow existing pattern. Settings page.tsx is `"use client"`, uses `useSession()` for auth data, `fetch()` for additional user data (Account providers, etc.).

## Updated Plan Amendments

1. All 3 new Prisma models get `user User @relation(fields: [userId], references: [id], onDelete: Cascade)` and User model gets corresponding relation arrays
2. Name edit → `router.refresh()` after PATCH, not just optimistic
3. Mobile: wire existing MobileTopBar avatar → `/settings` link. Desktop: ProfileIcon in sidebar footer.
4. No delete account button in v1
5. Page is `"use client"` matching dashboard pattern, not a server component
