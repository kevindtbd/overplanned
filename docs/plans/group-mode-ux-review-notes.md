# Group Mode UX — Plan Review Notes

**Reviewed**: 2026-02-23

## Findings

### Resolved During Review

1. **Race condition (invite API vs mode save)**: Non-issue. InviteCrewCard only renders after `fetchTrip` returns `mode: "group"`, meaning the DB write has already completed. No guard needed.

2. **Step count fatigue**: Combine mode selection into the name step instead of a separate step. Keeps onboarding at 8 steps instead of 9. Mode is just two toggle buttons — doesn't warrant its own screen.

3. **Dismiss scope on mode toggle**: Clear the sessionStorage dismiss flag when mode changes. If user goes group → solo → group, they see the invite card again. Prevents stale dismissals.

4. **Test strategy**: Update existing TripSettings tests for onModeChange callback AND create a separate GroupMode.test.tsx for group-specific behavior (invite card, toast, badge).

### No Issues Found

- **Invite API gating**: Already checks `trip.mode === "group"` server-side (line 70 of invite route). Correct.
- **Writable fields fix**: Already applied. `mode` is in `WRITABLE_BY_STATUS.planning`. Correct.
- **No schema changes needed**: Mode is already a string field on Trip. Correct.
- **No new API endpoints needed**: Invite endpoint already exists. Correct.

## Plan Amendments

1. ~~Separate ModeStep component~~ → Inline mode toggle in name step (no new step/component)
2. Add: clear `dismiss-invite-${tripId}` from sessionStorage when `onModeChange` fires
3. Add: both test strategies (update existing + new file)
