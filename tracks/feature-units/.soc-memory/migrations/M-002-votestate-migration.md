# M-002: voteState -> ownerTip Data Migration

## Description
Fix architect blocker B1: LLM enrichment writes `{ narrativeHint: "..." }` to `ItinerarySlot.voteState`. Vote API would overwrite this, causing data loss. Migrate existing data and update the write path.

## Task

### 1. Create data migration script
Create `scripts/migrate-vote-state.ts`:
- Query all ItinerarySlots where `voteState` is not null
- For each slot: if `voteState` contains `narrativeHint` key:
  - Copy `voteState.narrativeHint` to `ownerTip` field
  - Set `voteState = null`
- Use `prisma.$transaction` for atomicity
- Log count of migrated slots
- Script should be idempotent (skip slots where ownerTip is already set)

Run with: `npx tsx scripts/migrate-vote-state.ts`

### 2. Update LLM enrichment write path
Edit `apps/web/lib/generation/llm-enrichment.ts`:
- Find the line that writes `voteState: { narrativeHint: h.hint.slice(0, 100) }` (around line 97)
- Change to write `ownerTip: h.hint.slice(0, 100)` instead
- Remove any reference to `voteState` in the enrichment update call

### 3. Verify
- Run migration script against dev DB
- Confirm no slots have `narrativeHint` in voteState anymore
- Confirm enrichment still works: `npx tsc --noEmit`

## Output
scripts/migrate-vote-state.ts
apps/web/lib/generation/llm-enrichment.ts

## Zone
infra

## Dependencies
M-001

## Priority
95

## Target Files
- scripts/migrate-vote-state.ts
- apps/web/lib/generation/llm-enrichment.ts
