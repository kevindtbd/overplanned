# Server / Signals

## Three-Layer Signal Architecture
1. **BehavioralSignal** — User actions (clicks, swipes, saves, skips). For ML training ONLY user actions.
2. **IntentionSignal** — Why signals (explicit feedback, reflection ratings). Higher confidence.
3. **RawEvent** — Firehose (impressions, page views, session data). System events go here NOT BehavioralSignal.

## API Routes
- `app/api/signals/behavioral/route.ts` — Log behavioral signals
- `app/api/events/raw/route.ts` — Raw event ingestion
- `app/api/events/batch/route.ts` — Batch event send

## Key Rule
- **BehavioralSignal is for user actions only** — system events pollute ML training data
- Over-log, never under-log
- 9 new SignalType enum values added in feature units sprint

## Learnings
- (space for future compound learnings)
