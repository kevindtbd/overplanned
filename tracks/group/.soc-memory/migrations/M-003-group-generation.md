# M-003: Group Itinerary Generation

## Description
Generate itinerary for N members' combined preferences with fairness weighting.

## Task
1. Weighted vector: combine all members' personaSeeds into a weighted query vector
   - Equal weight initially, adjusted by fairness debt in subsequent rounds

2. Fairness-weighted ranking: balance slot selection across member preferences
   - No single member's preferences dominate

3. Same fallback cascade as solo (LLM timeout → deterministic → template)

4. Candidate set logged to RawEvent with per-member preference scores (who wanted what)

## Output
services/api/generation/group_engine.py

## Zone
generation

## Dependencies
- M-002

## Priority
80

## Target Files
- services/api/generation/group_engine.py
- services/api/generation/preference_merger.py

## Files
- services/api/generation/engine.py
- docs/plans/vertical-plans-v2.md
