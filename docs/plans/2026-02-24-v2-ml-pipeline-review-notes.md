# V2 ML Pipeline — Review Notes

## Date: 2026-02-24
## Status: All reviews complete, findings folded into design doc

---

## Review Pipeline

| Step | Status | Output |
|------|--------|--------|
| Brainstorm | Complete | 13 decisions made (design doc Decisions table) |
| Deepen | Complete | 10 issues examined, 2 critical, 4 gaps, 2 non-issues, 2 improvements |
| Architect review | Complete | APPROVE (2 concerns: missing index, completionSignal should be enum) |
| Security review | Complete | 1 FAIL (signal weight injection), 5 WARN, 1 PASS |
| Test engineer review | Complete | ~195 → ~254 tests, 6 gaps identified, CI mapping added |

All findings folded into `2026-02-24-v2-ml-pipeline-design.md`. This file is the audit trail.

---

## Deepen Findings

### Critical Issues (addressed in design doc)

1. **Arctic Shift Data Availability** — PRE-FLIGHT gate added to Wave B2. Verify before writing code, pay for data if needed.
2. **Exploration Budget** — Assigned to Phase 6 prerequisite. No feedback loop exists until ML models produce rankings.

### Gaps Clarified (addressed in design doc)

3. **PII in ChatGPT import** — Regex scrub + 90-day source_text TTL + `pii_scrubbed` flag added to ImportPreferenceSignal spec.
4. **Signal weight calibration** — Phase 1: hand-tuned defaults. Phase 6: models learn implicit weights. Phase 4.3: automated ablation.
5. **Write-back atomicity** — Single CTE transaction + `WriteBackRun` audit table added to Wave A spec.
6. **BPR contingency gate** — Hybrid: automated detection, manual decision, 7-day staleness alert.

### Non-Issues (validated)

7. **Migration rollback** — Postgres DDL is transactional. Existing mitigation sufficient.
8. **Synthetic/rejection recovery clash** — Source field gates it. Integration test added.

### Improvements (added to design doc)

9. **Shadow mode observability** — 3-layer monitoring + agreement drift added to Phase 4.2.
10. **Timeline reframing** — Build order, not calendar. Decision #13.

---

## Architect Review Findings

**Reviewer:** architect-review agent | **Verdict:** APPROVE (2 concerns)

| Area | Verdict | Action Taken |
|------|---------|-------------|
| Schema design | APPROVE | Added compound index on `BehavioralSignal.source`, changed `completionSignal` to Prisma enum |
| Wave execution | APPROVE | Zero file overlap verified against actual codebase — no changes needed |
| Signal architecture | APPROVE | `source`/`signal_weight`/`subflow` compose cleanly — no changes needed |
| Model progression | APPROVE | Added `ActivitySearchService` protocol/ABC pre-req note on Two-Tower |
| NO GPU policy | APPROVE | CPU-only validated at stated scale — no changes needed |

**Long-term watch:** BehavioralSignal table becoming central nervous system. At 500K+ rows, compound indexes + Parquet extraction (Phase 4.1) should be primary ML read path.

---

## Security Review Findings

**Reviewer:** security-auditor agent | **Verdict:** 1 FAIL, 5 WARN, 1 PASS

| # | Area | Verdict | Severity | Action Taken |
|---|------|---------|----------|-------------|
| 1 | ChatGPT Import (3.1) | WARN | High | ZIP bomb defense, path traversal, auth, consent check, streaming caps all added to Phase 3.1 spec |
| 2 | PII Handling | WARN | Medium | Regex scrub + 90-day TTL + `pii_scrubbed` flag added. Phase 2: evaluate spaCy NER |
| 3 | Synthetic Simulation (3.4) | WARN | Medium | Admin-only, $100/day cap, circuit breaker, synth- user ID prefix, defense-in-depth quarantine |
| 4 | Write-Back Job (2.2) | PASS | Low | Least-privilege DB role recommendation added |
| 5 | Shadow Mode (4.2) | WARN | Medium | Network isolation assertion, 180-day retention policy added |
| 6 | **Signal Weight** | **FAIL** | **High** | Server-only enforcement, DB CHECK `[-1.0, 3.0]`, per-user per-venue dedup, exclude from client Pydantic schema — ALL added to Wave A spec |
| 7 | ArbitrationEvent JSONB | WARN | Medium | 64KB CHECK constraint, Pydantic schema validation, no raw user text — added to Wave A spec |

**Cross-cutting:** Upload endpoint auth is placeholder (existing debt). Body size enforcement is path-specific. DataConsent model defined but never queried — must wire before ML training data storage.

---

## Test Engineer Review Findings

**Reviewer:** test-engineer agent | **Verdict:** Directionally correct, 6 gaps

| Category | Finding | Action Taken |
|----------|---------|-------------|
| Test count | Under by ~45 (~195 → ~254) | Revised counts in design doc, added chaos/degradation category |
| Unit boundary cases | Missing for Laplace, tourist correction, cascade limit, burst counter, subflow priority | Required boundary test suites listed in Tier 1 spec |
| Integration infra | No testcontainers (fine), no Qdrant in CI, no local compose | Use CI service containers + add Qdrant, write docker-compose.test.yml |
| Tier 3 operations | Triggering + monitoring unspecified | GH Actions cron (nightly), Cloud Scheduler (weekly), Slack webhook, artifact-triggered workflow |
| Missing categories | No load/perf, no chaos, incomplete data quality | Added chaos/degradation tests (~15), perf benchmarks at Wave merge |
| Test data | Strong factories, need V2 updates + new factories + golden fixtures | Factory updates in Wave A, golden fixtures in `tests/fixtures/` |
| CI mapping | No `ml` track, no scheduled workflow | CI integration table added to design doc |

**P0 tests (must have before each wave):**
- Wave B: Laplace boundary (5), subflow priority (8), factory updates
- Wave C: Tourist correction boundary (6), write-back idempotency (3), write-back atomicity (2)
- Wave D: ChatGPT import resilience (8), NLP extraction regression (5), burst counter degradation (3)
- Wave E: Shadow fire-and-forget (3), model forward pass shape (4/model), synthetic quarantine E2E (3)

---

## Summary

| Category | Count |
|----------|-------|
| Decisions made (brainstorm) | 13 |
| Deepen findings addressed | 10 |
| Architect concerns resolved | 2 |
| Security FAIL resolved | 1 |
| Security WARN mitigated | 5 |
| Test gaps addressed | 6 |
| Total test count (revised) | ~254 |

**The plan is reviewed and ready for execution.** All findings from three independent agent reviews have been folded into the design doc. No outstanding blockers except the Arctic Shift pre-flight verification (10 minutes, do first).
