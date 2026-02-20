# M-009: Mid-Trip Tests

## Description
Comprehensive test suite for mid-trip features.

## Task
1. Unit: trigger detection, cascade scope (same-day only), proximity calc, prompt parsing, keyword fallback, MAX_PIVOT_DEPTH
2. Integration: weather trigger → pivot → accept → cascade updates downstream
3. Integration: prompt bar → Haiku parse → PivotEvent → resolution → signals
4. E2E: active trip → trigger → resolve pivot → all signals captured
5. Prompt injection tests: malicious input rejected, structured output only
6. Cross-track: pivot signals visible to Track 6 post-trip disambiguation

## Output
services/api/tests/midtrip/conftest.py

## Zone
tests

## Dependencies
- M-008

## Priority
20

## Target Files
- services/api/tests/midtrip/conftest.py
- services/api/tests/midtrip/test_triggers.py
- services/api/tests/midtrip/test_cascade.py
- services/api/tests/midtrip/test_microstops.py
- services/api/tests/midtrip/test_prompt_bar.py
- services/api/tests/midtrip/test_trust.py
- apps/web/__tests__/e2e/midtrip.spec.ts

## Files
- docs/plans/vertical-plans-v2.md
