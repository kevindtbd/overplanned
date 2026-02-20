-- Migration: add_gist_index
-- Purpose: Create a PostGIS GIST index on ActivityNode lat/lon for fast
--          spatial proximity queries used by the micro-stop subsystem.
--
-- ST_MakePoint(longitude, latitude) follows PostGIS convention (X=lon, Y=lat).
-- SRID 4326 = WGS84 geographic coordinates.
--
-- This index accelerates ST_DWithin and ST_Within queries in
-- services/api/microstops/spatial.py.

-- Requires: PostGIS extension enabled in the database.
-- Run: psql $DATABASE_URL -f prisma/migrations/add_gist_index.sql

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE INDEX IF NOT EXISTS idx_activity_nodes_location
    ON "ActivityNode"
    USING GIST (
        ST_SetSRID(
            ST_MakePoint(longitude, latitude),
            4326
        )
    );

-- Secondary index: approved + canonical filter (frequent WHERE clause)
-- Partial index avoids indexing archived/flagged nodes
CREATE INDEX IF NOT EXISTS idx_activity_nodes_approved_canonical
    ON "ActivityNode" (id, "convergenceScore" DESC NULLS LAST)
    WHERE status = 'approved' AND "isCanonical" = true;

-- Composite index for itinerary slot lookups by trip + day (used in cascade + spatial queries)
CREATE INDEX IF NOT EXISTS idx_itinerary_slots_trip_day_order
    ON "ItinerarySlot" ("tripId", "dayNumber", "sortOrder" ASC)
    WHERE status NOT IN ('completed', 'skipped');
