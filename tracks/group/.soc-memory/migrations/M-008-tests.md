# M-008: Group Trip Tests

## Description
Full test suite for group trip features.

## Task
1. Unit: voting logic, fairness debt_delta, camp detection, Abilene paradox, token generation/validation
2. Integration: invite → signup → join → vote → resolve → fairness updates
3. Integration: SharedTripToken create → view → expire → revoke
4. E2E: full group trip lifecycle with 3 members
5. Token security: expired rejected, revoked rejected, max uses enforced
6. Cross-track: SlotCard works in group context, signals write correctly

## Output
services/api/tests/group/conftest.py

## Zone
tests

## Dependencies
- M-007

## Priority
20

## Target Files
- services/api/tests/group/conftest.py
- services/api/tests/group/test_voting.py
- services/api/tests/group/test_fairness.py
- services/api/tests/group/test_invites.py
- services/api/tests/group/test_shared_links.py
- apps/web/__tests__/group/GroupDashboard.test.tsx
- apps/web/__tests__/e2e/group.spec.ts

## Files
- docs/plans/vertical-plans-v2.md
