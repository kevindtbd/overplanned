# M-007: Pipeline Health + Cost Dashboard

## Description
LLM costs, API call counts, pipeline job health, cost alerting.

## Task
1. LLM costs by model, date, pipeline stage
2. API call counts (Foursquare, Google, OpenWeatherMap)
3. Pipeline success/failure rates
4. Cost alerting: configurable thresholds, alert on exceed

## Output
apps/web/app/admin/pipeline/page.tsx

## Zone
pipeline

## Dependencies
- M-001

## Priority
40

## Target Files
- apps/web/app/admin/pipeline/page.tsx
- services/api/routers/admin_pipeline.py

## Files
- docs/plans/vertical-plans-v2.md
