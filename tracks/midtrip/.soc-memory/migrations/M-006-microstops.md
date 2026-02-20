# M-006: Micro-Stops

## Description
Proximity-based suggestions during transit using PostGIS spatial queries.

## Task
1. Raw SQL migration: CREATE INDEX idx_activity_nodes_location ON activity_nodes USING GIST (ST_MakePoint(longitude, latitude))
2. Proximity query: find interesting nodes within 200m of transit path
3. Micro-stop as lightweight ItinerarySlot (slotType: flex, short duration 15-30min)
4. Surface: notification-style card during transit

## Output
services/api/microstops/service.py

## Zone
microstops

## Dependencies
- M-005

## Priority
50

## Target Files
- services/api/microstops/service.py
- services/api/microstops/spatial.py
- prisma/migrations/add_gist_index.sql

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
