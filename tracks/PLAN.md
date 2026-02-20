# Overplanned — SOC Execution Plan

## 7 Tracks, 71 Migrations

| Track | Directory | Migrations | Phase | Parallel With |
|-------|-----------|-----------|-------|---------------|
| Foundation | tracks/foundation/ | 12 | 1 | — |
| Data Pipeline | tracks/pipeline/ | 14 | 2a | Admin |
| Admin | tracks/admin/ | 9 | 2b | Pipeline |
| Solo Trip | tracks/solo/ | 11 | 3 | — |
| Group Trip | tracks/group/ | 8 | 4a | Mid-Trip |
| Mid-Trip | tracks/midtrip/ | 9 | 4b | Group Trip |
| Post-Trip | tracks/posttrip/ | 8 | 5 | — |

## How to Run

Each track is a separate `conductor run`. Execute in phase order.

### Phase 1
```bash
conductor run tracks/foundation -d -v --web-port 8888 -w 5
```

### Phase 2 (parallel — two terminals)
```bash
# Terminal 1
conductor run tracks/pipeline -d -v --web-port 8889 -w 5

# Terminal 2
conductor run tracks/admin -d -v --web-port 8890 -w 5
```

### Phase 3
```bash
conductor run tracks/solo -d -v --web-port 8888 -w 5
```

### Phase 4 (parallel — two terminals)
```bash
# Terminal 1
conductor run tracks/group -d -v --web-port 8889 -w 5

# Terminal 2
conductor run tracks/midtrip -d -v --web-port 8890 -w 5
```

### Phase 5
```bash
conductor run tracks/posttrip -d -v --web-port 8888 -w 5
```

### Phase 6: Cross-Track Tests
Run manually after all tracks merge to main:
```bash
pytest tests/cross-track/ -v
```

## Between Phases
1. Review conductor CHANGELOG for completed phase
2. Run full regression: `make test`
3. Course-correct plans for next phase if needed
4. Commit + push completed work

## Reference Docs
- Detailed plans: docs/plans/vertical-plans-v2.md
- Execution order: docs/plans/execution-order.md
- Deferred items: docs/plans/phase-2-and-non-mvp-sidebar.md
- Schema contracts: memory/schema-contracts.md + memory/schema-revisions.md
