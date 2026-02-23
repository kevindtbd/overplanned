# Data / Privacy & GDPR

## Implemented
- `app/api/settings/export/route.ts` — GDPR data export
- `app/api/settings/privacy/route.ts` — Privacy controls
- Content purge job: rawExcerpt > 30 days -> null (compliance)

## Design Docs
- `docs/plans/2026-02-22-privacy-data-design.md`
- `docs/plans/2026-02-22-privacy-data-implementation.md`
- `docs/overplanned-data-sanitation.md`

## Principles
- No demographic profiling (no age, home city, income fields)
- Content purge for scraped excerpts
- User-facing privacy controls in settings
- Data export in standard format

## Learnings
- (space for future compound learnings)
