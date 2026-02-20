# M-001: Docker + PostGIS + Redis

## Description
Set up the complete local development infrastructure. All services containerized, bound to localhost only, with env var substitution and no hardcoded secrets.

## Task
Create docker-compose.yml with:
- Postgres 16 with PostGIS extension (port 5432, localhost only)
- Redis 7 Alpine with password auth (port 6379, localhost only)
- Qdrant with API key auth (ports 6333/6334, localhost only)
- PgBouncer for connection pooling (port 6432, localhost only)
- Named volumes for all data directories
- All passwords via env vars with required flags (no defaults for secrets)

Create .env.example documenting all required environment variables:
- POSTGRES_PASSWORD (required)
- POSTGRES_DB (default: overplanned)
- POSTGRES_USER (default: overplanned)
- REDIS_PASSWORD (required)
- QDRANT_API_KEY (required)

Create init script that enables PostGIS extension on first boot:
- docker-entrypoint-initdb.d/init-postgis.sql with CREATE EXTENSION IF NOT EXISTS postgis;

Verify: `docker compose up` → all 4 services healthy, `SELECT PostGIS_version()` returns a version.

## Output
docker-compose.yml

## Zone
infra

## Dependencies
none

## Priority
100

## Target Files
- docker-compose.yml
- .env.example
- docker/init-postgis.sql

## Files
- docs/plans/vertical-plans-v2.md
- docs/plans/execution-order.md
