# M-008: Trust Recovery

## Description
Flag mechanism for bad recommendations with separate "wrong for me" vs "wrong information" paths.

## Task
1. Flag sheet on slot card (showFlag=true prop)
2. "Wrong for me" → IntentionSignal (source: user_explicit, confidence: 1.0) + BehavioralSignal
3. "Wrong information" → ActivityNode flagged for admin review queue (Track 7)
4. Both paths write appropriate signals

## Output
apps/web/components/trust/FlagSheet.tsx

## Zone
trust

## Dependencies
- M-004

## Priority
40

## Target Files
- apps/web/components/trust/FlagSheet.tsx
- apps/web/components/trust/ResolutionPicker.tsx

## Files
- apps/web/components/slot/SlotCard.tsx
- docs/plans/vertical-plans-v2.md
