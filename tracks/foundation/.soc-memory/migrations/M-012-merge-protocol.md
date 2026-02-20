# M-012: Migration Merge Protocol

## Description
Document the schema change protocol that all tracks must follow when extending the Prisma schema. This prevents migration conflicts when parallel tracks modify the same tables.

## Task
1. Write CONTRIBUTING.md with:
   - Schema change rules:
     - All schema changes go through a PR against main
     - PRs that modify schema.prisma MUST run codegen and commit generated files
     - All track tests must pass on the PR (regression gate)
     - Schema changes are reviewed by at least one other track owner

   - Branch strategy:
     - Each track works on its own branch (track/foundation, track/pipeline, etc.)
     - Schema extensions (Track 4/5 adding fields to existing tables) go to main first
     - Rebase track branch onto main after schema merge

   - PR template for schema changes (.github/pull_request_template.md):
     - Checklist: codegen run, contract tests pass, no breaking changes to other tracks
     - Required: list of affected models, new fields, new indexes

   - Conflict resolution:
     - If two tracks modify the same model: earlier-numbered track merges first
     - Later track rebases and resolves
     - Prisma migration squash if conflicts arise

2. GitHub Actions workflow (.github/workflows/regression.yml):
   - On every PR to main: run ALL track test suites
   - If Track 5 breaks a Track 3 test, Track 5 owns the fix

Deliverable: CONTRIBUTING.md with schema change protocol. PR template. Regression gate CI.

## Output
CONTRIBUTING.md

## Zone
monorepo

## Dependencies
- M-011

## Priority
30

## Target Files
- CONTRIBUTING.md
- .github/pull_request_template.md
- .github/workflows/regression.yml

## Files
- docs/plans/vertical-plans-v2.md
- docs/plans/execution-order.md
