# Overplanned — Navigation Architecture

*Last updated: February 2026*
*Decision: Option 2 hybrid — focused trip context, one-tap escape, app nav returns on exit*

---

## The Model

Two distinct navigation contexts. The transition between them is the only moment both exist simultaneously.

```
APP CONTEXT                          TRIP CONTEXT
─────────────────                    ─────────────────────────
Bottom nav: always visible           Bottom nav: hidden
Home / Trips / Explore / Profile     Trip tabs: Day / Map / Cal / Chat

Header: wordmark + search            Header: ← back + trip name + overflow
```

The app never shows both navs at once. Entering a trip hides the app nav. Exiting restores it.

---

## App Context — Bottom Nav

Four items. Always visible outside of a trip.

```
[ Home ]  [ Trips ]  [ Explore ]  [ Profile ]
```

- **Home** — dashboard. Upcoming trip hero, prep cards, persona, past trips.
- **Trips** — list of all trips (active, upcoming, past). Entry point to any trip.
- **Explore** — inspiration surface. Cold start vibe prompts or returning user confident guess.
- **Profile** — account, preferences, packing lists, notifications.

Active trip badge on **Trips** icon when a trip is in-progress today.

---

## Trip Context — Internal Navigation

### Header
```
← Japan 2025          Kyoto · Day 4 of 7          ···
```
- Left: back arrow + trip name. One tap exits trip, returns to app context (dashboard or trips list, whichever was last).
- Center: destination + day counter. Tappable — opens day picker.
- Right: overflow (share, export .ics, settings).

### Trip tabs
Live just below the hero image. Four tabs, text labels, no icons at this level — space is constrained.

```
[ Day ]  [ Map ]  [ Calendar ]  [ Chat ]
```

Sit on top of the hero photo as a translucent bar — same treatment as current solo view day strip. Consistent with existing design.

### No persistent app nav inside a trip
User is traveling. They don't need Home or Explore while mid-trip. If they want to switch trips, they tap ← to exit and navigate from the Trips tab. One extra tap is acceptable — the focused context is worth it.

---

## Transitions

### Entering a trip
Dashboard hero card → tap "Open trip" → trip view slides up (vertical sheet push, not horizontal). App nav fades out. Trip header fades in.

### Exiting a trip
Tap ← in trip header → trip view slides down. App nav fades in. Returns to last app context.

### Switching trips without fully exiting
Not supported in v1. User taps ←, goes to Trips tab, taps different trip. Acceptable friction — trip-switching mid-session is rare.

---

## Edge Case: Active Trip Notification Tap

User receives morning briefing push notification → taps it → opens directly into trip view (bypassing app context entirely). Back arrow exits to home screen or last app used. Standard iOS/Android deep link behavior.

---

## Responsive — Desktop

Desktop has a persistent left sidebar (already built in dashboard). Trip view uses the same sidebar. No bottom nav on desktop — sidebar handles app-level navigation. Trip tabs move to a horizontal tab bar below the trip hero in the main content area.

```
[Sidebar: nav + trips]  [Trip hero + day tabs]  [Context panel: map/detail]
```

---

## What This Resolves

| Problem | Resolution |
|---|---|
| Two navs competing | App nav hides inside trip. Never both visible. |
| How to exit trip | ← arrow always visible top-left. One tap. |
| Trip tabs location | Below hero, existing treatment. Unchanged. |
| Deep link from notification | Opens trip directly. ← exits to OS. |
| Desktop | Sidebar handles app nav. Trip tabs in main area. |

---

## What This Does NOT Cover (Future)

- Subgroup split navigation (one member on a different day track) — tracked in group dynamics doc
- Trip sharing / view-only link — no nav state needed, read-only surface
- Offline nav behavior — app nav still renders, trip tabs still render, back arrow still works. Network state affects content only.
