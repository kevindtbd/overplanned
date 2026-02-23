# Data Vertical — Memory Bank

## Sub-topic Files
- `schema.md` — Prisma models, migrations, schema contracts
- `pipeline.md` — Scrapers, entity resolution, data ingestion
- `privacy.md` — GDPR, data sanitation, content purge, export

## Key Principles
- No column without a data source — if nothing writes at launch, it doesn't exist
- Over-log, never under-log
- Per-source quality signals — NEVER collapse to single score
- Raw SQL tables must be in Prisma schema or `prisma db push` drops them
