# Settings V2 — Plan Review Notes

## Issues Found & Resolutions

### 1. Stripe ID leaks to client (SECURITY)
**Problem:** Plan says "pass stripeCustomerId from session to SubscriptionBadge" but this exposes a Stripe internal ID to every page load via the session object.
**Resolution:** Fetch on click. The "Manage billing" button always renders for non-free tiers. On click, POST to `/api/settings/billing-portal`, which checks `stripeCustomerId` server-side. If null, return 404 with friendly message. No session callback changes needed.

### 2. stripeCustomerId not in NextAuth session (BLOCKER)
**Problem:** The session callback (`lib/auth/config.ts:57-61`) only exposes `id`, `subscriptionTier`, `systemRole`. Plan assumed it was available.
**Resolution:** Moot — fetch-on-click pattern means we never need it in the session. The POST route does its own DB lookup.

### 3. PreferencesSection would balloon to 600+ lines (ARCHITECTURE)
**Problem:** Plan puts display prefs + vibe tags + textarea into the existing 330-line PreferencesSection.
**Resolution:** Split into 3 components:
- `PreferencesSection` — existing dietary/mobility/languages/frequency (unchanged)
- `DisplayPreferences` — units, date/time, theme (new component, new section)
- `TravelInterests` — vibe tags + free-form textarea (new component, new section)

Settings page section order becomes:
1. Account
2. Subscription + Stripe portal
3. Display Preferences (new)
4. My Preferences (existing)
5. Travel Interests (new)
6. Notifications (enhanced)
7. Privacy & Data
8. About

### 4. Theme flash-of-wrong-theme — hydration mismatch (BUG)
**Problem:** Plan uses inline `<script>` to read theme cookie and set `data-theme`. But Next.js SSR renders `<html>` without the attribute, then the script adds it before hydration — React sees a mismatch.
**Resolution:** Read theme cookie server-side in `layout.tsx` (it's a server component). Render `<html data-theme={theme}>` during SSR. Zero flash, zero hydration mismatch. Client-side toggle updates both cookie + DOM attribute.

### 5. Textarea debounce causes excessive PATCHes (PERFORMANCE)
**Problem:** The 500ms debounce pattern works for discrete chip clicks but fires on every typing pause in the textarea. A 200-char note = 5-10 PATCHes.
**Resolution:** Textarea saves on blur only (same pattern as account name input). Vibe tag chips keep the 500ms debounce.

### 6. preTripDaysBefore visibility when tripReminders is off (UX)
**Problem:** Plan doesn't specify what happens to the "Remind me before trips" selector when the parent toggle (tripReminders) is disabled.
**Resolution:** Hide but preserve. Value stays in DB. Re-enabling tripReminders shows previous selection.

### 7. Display prefs stored but nothing reads them (DEAD CODE)
**Problem:** Plan creates 5 display preference fields but no code consumes them. Settings that don't do anything visible.
**Resolution:** Build UI AND wire consumers. Update .ics export to use dateFormat/timeFormat. Update any existing time display in slot cards to respect format preferences. This expands scope but ensures the settings actually work.

## No Issues Found With
- Vibe tag curation (23 tags from 42 vocabulary is well-reasoned)
- Schema migration approach (all defaults, no data migration)
- checkinReminder as opt-in (matches product doc)
- Zod validation patterns (consistent with existing)
- Server-side array deduplication on vibePreferences
- travelStyleNote max length (500 chars)
- ML extraction deferred to future async job
