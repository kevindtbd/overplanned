# M-005: Fairness Engine

## Description
Concrete, testable fairness algorithm that prevents one person from dominating group choices.

## Task
1. debt_delta = member_preference_rank - group_choice_rank per member per vote
2. Accumulate debt per member in Trip.fairnessState
3. Next conflict: weight alternatives by inverse cumulative debt (most-compromised member gets boosted)
4. Abilene paradox detection: if ALL votes are lukewarm (enthusiasm < 0.4 for all members), trigger dissent prompt ("Is anyone actually excited about this?")
5. Deterministic: same input → same output (testable with fixed seeds)

## Output
services/api/group/fairness.py

## Zone
fairness

## Dependencies
- M-004

## Priority
60

## Target Files
- services/api/group/fairness.py
- services/api/group/abilene_detector.py

## Files
- docs/plans/vertical-plans-v2.md
