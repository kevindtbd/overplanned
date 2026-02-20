# M-003: IntentionSignal from Post-Trip Feedback

## Description
Capture explicit skip reasons as IntentionSignals for training.

## Task
1. Options: "not interested" | "bad timing" | "too far" | "already visited" | "weather" | "group conflict"
2. Write IntentionSignal: source="user_explicit", confidence=1.0, intentionType from selection
3. These are the highest-confidence training signals we get.

## Output
services/api/posttrip/intention_signal.py

## Zone
signals

## Dependencies
- M-002

## Priority
80

## Target Files
- services/api/posttrip/intention_signal.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
