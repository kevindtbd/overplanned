# Plan Review Notes: BPR Training Blockers

*Reviewed: 2026-02-20*
*Reviewer: deepen-plan*

---

## Refinements Applied

### 1. RankingEvent candidateIds capped to top 20
**Original:** Store all ActivityNodes in the city (20-73 per array).
**Refined:** Top 20 by affinity per day. Mirrors realistic "model scored
and filtered" UI behavior. Produces tighter negatives for BPR training.
Math: ~15K events * 5 selected from 20 candidates = ~1.1M training triples.

### 2. Validation query fixed with dayNumber join
**Original:** LEFT JOIN RankingEvent on (tripId, userId) — fans out because
one RankingEvent per day but many BehavioralSignals per day.
**Refined:** 3-way join through ItinerarySlot to get dayNumber, then join
RankingEvent on (tripId, userId, dayNumber). Filter on slotId IS NOT NULL.

### 3. Affinity source for RankingEvent seeder
**Decision:** Read PersonaDimension rows, NOT Trip.personaSeed JSON.
Single source of truth. Validates materialization pipeline end-to-end.
Requires PersonaDimension to be seeded before RankingEvents (already in
implementation order).

### 4. Idempotency strategy
**Decision:** DELETE + re-INSERT for shadow data (PersonaDimension and
RankingEvent). ModelRegistry backfill uses WHERE modelVersion IS NULL
(already idempotent). Clean slate on re-run allows tweaking affinity
math without stale data mixing.

---

## No Critical Issues Found

The design is tight. Three tables, clear seeding order, validation query
that exercises all joins. Shadow mode fields on RankingEvent are forward-
looking but zero-cost (nullable, empty arrays).

---

## Ready for Agent Review

Recommend dispatching: backend-architect, data-scientist, security-auditor.
Focus areas:
- backend-architect: Schema design, index coverage, query performance
- data-scientist: Training triple quality, affinity recomputation correctness
- security-auditor: Backfill UPDATE safety, shadow user data isolation
