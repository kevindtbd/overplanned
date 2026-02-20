# M-004: Async Voting

## Description
Slot voting UI for group members to propose, vote, and resolve contested slots.

## Task
1. Vote states: proposed → voting → confirmed/contested
2. Camp detection: when members split on a slot
3. Conflict resolution: show alternatives from ActivitySearchService, re-vote
4. Update ItinerarySlot.voteState and isContested
5. Uses SlotCard component with showVoting=true prop

## Output
apps/web/components/group/voting/VotePanel.tsx

## Zone
voting

## Dependencies
- M-003

## Priority
70

## Target Files
- apps/web/components/group/voting/VotePanel.tsx
- apps/web/components/group/voting/CampDetector.tsx
- apps/web/components/group/voting/ConflictResolver.tsx

## Files
- apps/web/components/slot/SlotCard.tsx
- docs/plans/vertical-plans-v2.md
