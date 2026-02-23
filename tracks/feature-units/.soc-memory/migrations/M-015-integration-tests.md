# M-015: Cross-Track Integration Tests

## Description
Integration tests that verify cross-track interactions work correctly. These test the seams between features.

## Task

### 1. Create integration test file (`apps/web/__tests__/api/feature-units-integration.test.ts`)

Write the following cross-track integration tests:

**Invite -> Vote (new member can immediately vote):**
- Simulate: user joins via invite (M-004), then casts vote on a slot (M-005)
- Verify: new member's vote is counted in quorum
- Verify: new member appears in voteState.votes

**Import -> Reflection (reflection works on cloned trips):**
- Simulate: user imports a shared trip (M-006), trip status changed to completed, user submits reflection (M-007)
- Verify: reflectionData stored on the cloned trip (not the original)
- Verify: signal logged with correct tripId (cloned, not original)

**Vote quorum after invite:**
- Setup: 2-member trip, 1 slot with 1 vote already cast
- Simulate: 3rd member joins via invite
- Verify: quorum now requires 3 votes (not 2), slot doesn't auto-confirm with only 1 vote
- Verify: if original 2 voted yes (66%), slot is NOT confirmed (need 70%)

**Pivot on voted slot (voteState resets after swap):**
- Setup: slot with confirmed voteState (all members voted yes)
- Simulate: create pivot (M-009), accept pivot with new node
- Verify: slot.voteState is reset to null
- Verify: slot.isContested is reset to false
- Verify: slot.status reset to proposed or keep confirmed? (check plan — keep as confirmed per swap behavior)

### 2. Test infrastructure
- These tests may need more complex mock setups than single-track tests
- Use the auth factory and transaction mock from M-003
- Each test should be self-contained (no test interdependencies)

### 3. Test count
- Target: 10-15 integration tests
- Focus on the 4 cross-track scenarios identified in review

## Output
apps/web/__tests__/api/feature-units-integration.test.ts

## Zone
test

## Dependencies
M-010, M-011, M-012, M-013, M-014

## Priority
40

## Target Files
- apps/web/__tests__/api/feature-units-integration.test.ts

## Files
- docs/plans/2026-02-22-feature-units-review-notes.md (cross-track test scenarios)
