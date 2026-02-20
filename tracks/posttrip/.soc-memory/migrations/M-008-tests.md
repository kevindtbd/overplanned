# M-008: Post-Trip Tests

## Description
Full test suite for post-trip features.

## Task
1. Unit: timezone-aware completion (freeze_time across zones), disambiguation rules, photo upload validation
2. Integration: trip completes → reflection → signals + intentions written
3. Integration: disambiguation batch produces correct IntentionSignals
4. Integration: slot status override (completed → skipped) works
5. E2E: full trip lifecycle ending with post-trip, re-engagement verified
6. Cross-track: pivot signals from Track 5 visible in disambiguation

## Output
services/api/tests/posttrip/conftest.py

## Zone
tests

## Dependencies
- M-007

## Priority
20

## Target Files
- services/api/tests/posttrip/conftest.py
- services/api/tests/posttrip/test_completion.py
- services/api/tests/posttrip/test_reflection.py
- services/api/tests/posttrip/test_disambiguation.py
- services/api/tests/posttrip/test_reengagement.py
- apps/web/__tests__/e2e/posttrip.spec.ts

## Files
- docs/plans/vertical-plans-v2.md
