# UI / Admin

## Pages
- `app/admin/layout.tsx` — Admin layout + auth guard
- `app/admin/models/page.tsx` — Model registry UI
- `app/admin/models/components/PromotionGate.tsx` — Model promotion workflow
- `app/admin/seeding/page.tsx` — City seeding control
- `app/admin/nodes/page.tsx` — Activity node review queue
- `app/admin/nodes/components/NodeEditor.tsx` — Node edit form
- `app/admin/sources/page.tsx` — Source freshness dashboard
- `app/admin/users/page.tsx` — User lookup
- `app/admin/users/[id]/page.tsx` — User detail / persona inspector
- `app/admin/pipeline/page.tsx` — Pipeline health + cost dashboard
- `app/admin/safety/page.tsx` — Trust & safety
- `app/admin/safety/components/InjectionQueue.tsx` — Injection detection queue
- `app/admin/safety/components/TokenManager.tsx` — Token management

## Known Issues
- `@/lib/auth` barrel import doesn't exist (only individual files: config.ts, gates.ts, session.ts)
- AdminLayout tests fail because of this import — NOT related to UI overhaul

## Learnings
- (space for future compound learnings)
