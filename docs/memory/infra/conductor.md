# Infra / Conductor & SOC

## Config That Works
- workers: 5, model: claude-opus-4-6, budget_usd: 500
- root_dir: ../../ (resolves as effectiveWorkDir in main.go)
- retry with backoff, silence_timeout_ms: 120000

## Root Dir Fix
- Bug: conductor sets cmd.Dir to track path, but Claude writes to project root
- Fix: `root_dir: ../../` in conductor.yaml
- Binary rebuilt at `/home/pogchamp/soc-conductor/conductor`

## Execution Patterns
- **Schema migrations must be SOLO** — never in parallel wave
- **Wave-based execution prevents merge conflicts** — serialize tracks touching same file
- **Hard-scope each agent to ONLY its files** — "coordinate with Agent 2" is too weak
- Workers hallucinate when schema gate interrupts — downstream workers run anyway

## Agent Review Catches 3 Classes
1. Architect — correctness/patterns
2. Security — IDOR/injection/orphans
3. Test-engineer — assertion breakage
All non-overlapping.

## CRITICAL Rule
- When conductor deadlocks/fails, PRESENT THE FIX to user first
- Do NOT silently route around with manual Task agents
- Manual agents = zero conductor logging = blind spots
- Always kill old conductor processes before starting new ones on same port

## Learnings
- Cleanup for rogue changes: cross-reference modified files against plan's target list
- Schema INTERRUPT caused cascade hallucinations in feature units sprint
