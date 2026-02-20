# M-012: Content Purge Job

## Description
Scheduled job to delete raw excerpts after 30 days for compliance (Reddit content addendum).

## Task
Create services/api/pipeline/content_purge.py:
- Delete QualitySignal.rawExcerpt WHERE extractedAt > 30 days ago
- Do NOT delete the QualitySignal row itself — just null the rawExcerpt field
- Vibe tags, scores, and all derived data preserved
- Run as scheduled job (daily)
- Log: count of purged excerpts, execution time

Deliverable: cron runs, old excerpts nulled, all derived data preserved.

## Output
services/api/pipeline/content_purge.py

## Zone
maintenance

## Dependencies
- M-010

## Priority
30

## Target Files
- services/api/pipeline/content_purge.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
