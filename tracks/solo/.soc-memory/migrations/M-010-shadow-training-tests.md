# M-010: Shadow Training Validation Tests

## Description
Dedicated test suite validating that all shadow training data is being captured correctly for future ML training.

## Task
Create services/api/tests/shadow_training/test_training_data_quality.py:

1. Positive pair tests:
   - slot_confirm + activityNodeId present → valid positive pair
   - slot_complete + activityNodeId → valid positive
   - post_loved signal → valid positive

2. Explicit negative tests:
   - slot_skip → valid explicit negative
   - swipe_left → valid explicit negative
   - post_disliked → valid explicit negative

3. Implicit negative tests:
   - Impression without subsequent tap within session = implicit negative
   - Verify impression RawEvents have activityNodeId

4. Candidate set tests:
   - Generation logs full ranked pool as RawEvent
   - Rejected candidates (ranked but not selected) count > selected count
   - Candidate set has activityNodeIds and scores

5. Position bias tests:
   - Impression events include position field (1-indexed)
   - Position field is integer, not null

6. Session sequence tests:
   - Events within a session are ordered by timestamp
   - sessionId is consistent across a browsing session

7. Signal integrity:
   - Run assert_signal_integrity(db) after full flow
   - No orphan signals (all FKs valid)
   - Required fields present on all signals

## Output
services/api/tests/shadow_training/test_training_data_quality.py

## Zone
tests

## Dependencies
- M-008

## Priority
30

## Target Files
- services/api/tests/shadow_training/test_training_data_quality.py
- services/api/tests/shadow_training/conftest.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
