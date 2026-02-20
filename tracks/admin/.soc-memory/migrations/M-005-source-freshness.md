# M-005: Source Freshness Dashboard

## Description
Monitor scraper health and source freshness.

## Task
1. Last scrape time per source
2. Alert if stale (configurable threshold)
3. Authority score management (logged to AuditLog)

## Output
apps/web/app/admin/sources/page.tsx

## Zone
sources

## Dependencies
- M-001

## Priority
60

## Target Files
- apps/web/app/admin/sources/page.tsx
- services/api/routers/admin_sources.py

## Files
- docs/plans/vertical-plans-v2.md
