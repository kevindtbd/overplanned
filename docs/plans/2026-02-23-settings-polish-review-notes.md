# Settings Polish — Deepen Review Notes

## Critical Issues

### 1. Debounce race condition in PreferencesSection
`save()` sends the **entire PrefsState** on every chip toggle with a 500ms debounce. If user toggles dietary chip then immediately clicks accommodation chip within 500ms, the second debounce cancels the first — only accommodation gets saved, dietary change is lost.

**Fix:** Change to per-field PATCH (same pattern as NotificationsSection — send only the changed field). Or track dirty fields and merge into a single PATCH.

### 2. GDPR export missing fields (pre-existing + new)
`export/route.ts` line 58 only selects `dietary, mobility, languages, travelFrequency` from UserPreference. Missing:
- `vibePreferences`, `travelStyleNote` (already in schema, never added to export)
- 5 new fields: `budgetComfort`, `spendingPriorities`, `accommodationTypes`, `transitModes`, `preferencesNote`

Also missing from NotificationPreference export: `checkinReminder`, `preTripDaysBefore`

### 3. Consent banner text assumes defaults = actual state
Banner says "Both options below are currently enabled" but existing users with `modelTraining: false` will see incorrect text. Banner should check actual consent state or only show to users without an existing DataConsent row.

**Fix:** Render banner only when `localStorage` flag is absent AND either (a) no DataConsent row exists (fresh user) or (b) both fields are actually true. Simplest: just skip "Both options below are currently enabled" line, or make it conditional.

### 4. Schema migration coupling
Combining preferences expansion + consent default changes in one migration means legal rollback of consent defaults drags back preferences too.

**Recommendation:** Two separate migrations. Low cost, high optionality.

## Minor Gaps

### 5. LLM injection comment on preferencesNote
`travelStyleNote` has a security comment in the Zod schema. `preferencesNote` is identical in risk — free-form text fed to persona extraction. Needs the same `<user_note>` delimiter isolation comment.

### 6. Budget comfort needs null/"No preference" option
Design doc shows 4 radio options but no deselect. `travelFrequency` already has "No preference" (null). Budget should match to avoid forcing a choice.

### 7. Export fallback defaults stale
Line 133 in export route has hardcoded fallback for preferences that doesn't include vibePreferences or travelStyleNote. Will be further stale after adding 5 more fields. Should align with DEFAULTS from preferences route.
