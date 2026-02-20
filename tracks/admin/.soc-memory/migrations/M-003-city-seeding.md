# M-003: City Seeding Control

## Description
Trigger and monitor city seeding from admin UI.

## Task
1. Trigger seed job with confirmation + estimated cost
2. Progress dashboard per city
3. Rate limit: 2 seed triggers per minute

## Output
apps/web/app/admin/seeding/page.tsx

## Zone
seeding

## Dependencies
- M-001

## Priority
80

## Target Files
- apps/web/app/admin/seeding/page.tsx
- services/api/routers/admin_seeding.py

## Files
- docs/plans/vertical-plans-v2.md
