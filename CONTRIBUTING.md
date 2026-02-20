# Contributing to Overplanned

## Schema Change Protocol

All tracks share a single Prisma schema. This protocol prevents migration conflicts when parallel tracks modify the same tables.

### Rules

1. **All schema changes go through a PR against `main`.**
   - No direct pushes to `main` for schema modifications.
   - Track branches pull schema changes from `main`, never the reverse.

2. **PRs that modify `schema.prisma` MUST run codegen and commit generated files.**
   ```bash
   npx prisma generate
   npx prisma migrate dev --name <descriptive_name>
   ```
   Commit the resulting files in `prisma/migrations/` and any generated client output.

3. **All track tests must pass on the PR (regression gate).**
   - CI runs every track's test suite against schema change PRs.
   - If your schema change breaks another track's tests, you own the fix.

4. **Schema changes require review by at least one other track owner.**
   - The reviewer must be from a different track than the author.
   - Reviewer checks: no field collisions, no broken foreign keys, no index conflicts.

### Branch Strategy

- Each track works on its own branch: `track/foundation`, `track/pipeline`, `track/admin`, `track/solo`, `track/group`, `track/midtrip`, `track/posttrip`.
- **Schema extensions** (e.g., Track 4/5 adding fields to existing tables) go to `main` first via PR.
- After a schema PR merges to `main`, rebase your track branch onto `main`:
  ```bash
  git checkout track/<your-track>
  git rebase main
  ```
- Never merge track branches into each other. All shared state flows through `main`.

### Conflict Resolution

1. **Same-model conflicts**: The earlier-numbered track merges first.
   - Track 1 (Foundation) before Track 2 (Pipeline) before Track 3 (Admin), etc.
2. **Later track rebases and resolves** any conflicts against the merged state.
3. **Prisma migration squash** if migration files conflict:
   ```bash
   npx prisma migrate resolve --rolled-back <conflicting_migration>
   npx prisma migrate dev --name <squashed_name>
   ```
4. If resolution is unclear, open a discussion issue tagging both track owners before merging.

### What Counts as a Schema Change

- Adding, removing, or renaming a model
- Adding, removing, or renaming a field on any model
- Changing field types, defaults, or constraints
- Adding or modifying indexes or unique constraints
- Adding or modifying relations between models
- Changes to `prisma/schema.prisma` or any file in `prisma/migrations/`

### Commit Message Convention

Schema change commits use the prefix `schema:`:

```
schema: add pivot_events table for real-time trip reactivity
schema: add source_quality_json field to QualitySignal
schema: create index on behavioral_signals(user_id, created_at)
```

### PR Checklist (Quick Reference)

Before opening a schema PR, confirm:

- [ ] `npx prisma generate` ran without errors
- [ ] `npx prisma migrate dev` created a clean migration
- [ ] Generated files are committed
- [ ] Contract tests pass (`npm run test:contracts`)
- [ ] No breaking changes to other tracks' interfaces
- [ ] PR description lists affected models, new fields, and new indexes
- [ ] At least one reviewer from a different track is assigned

## General Development

### Running Tests

```bash
# All tests
npm test

# Single track
npm run test:foundation
npm run test:pipeline
npm run test:admin
npm run test:solo
npm run test:group
npm run test:midtrip
npm run test:posttrip

# Contract tests only
npm run test:contracts
```

### Code Style

- TypeScript for frontend and shared packages
- Python for FastAPI backend services
- No separate CSS/JS files — single-file components
- No emoji anywhere in the product
- Follow the locked design system (see `docs/overplanned-design-v4.html`)

### Key Principles

- **No column without a data source** — if nothing writes to a field at launch, it does not exist in the schema.
- **Three-layer signals** — BehavioralSignal (actions), IntentionSignal (why), RawEvent (firehose). Never mix actions and intentions.
- **Per-source quality signals** — never collapse to a single score.
- **Over-log, never under-log.**
