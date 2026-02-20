# M-004: Signal Disambiguation Batch

## Description
Rule-based batch job that infers IntentionSignals from BehavioralSignals + context.

## Task
1. Rules config (JSON, not ad-hoc if/else):
   - (post_skipped, rain, outdoors) → weather_dependent (0.7)
   - (post_skipped, clear, dining) → not_interested (0.6)
   - (post_skipped, time_overrun) → bad_timing (0.8)
2. Write IntentionSignal: source="rule_heuristic", confidence from rules
3. Explicit user feedback (M-003) always wins on read (higher confidence)
4. Process full backlog on first run

## Output
services/api/posttrip/disambiguation.py

## Zone
signals

## Dependencies
- M-003

## Priority
70

## Target Files
- services/api/posttrip/disambiguation.py
- services/api/posttrip/disambiguation_rules.json

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
