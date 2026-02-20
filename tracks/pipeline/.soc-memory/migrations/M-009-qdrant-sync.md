# M-009: Qdrant Sync + Embedding

## Description
Generate embeddings and sync ActivityNodes to Qdrant vector database.

## Task
Create services/api/pipeline/qdrant_sync.py:
- Generate embeddings via nomic-embed-text-v1.5 (768 dim) using EmbeddingService from Foundation M-010
- Text for embedding: concat(name, description, top_vibe_tags, category)
- Load to Qdrant activity_nodes collection:
  - Vector: 768-dim embedding
  - Payload: id, city, category, priceLevel, convergenceScore, authorityScore, vibeTagSlugs, isCanonical
  - Distance: Cosine
- Qdrant API key auth on all calls
- Sync job modes:
  - Full sync: all canonical nodes
  - Incremental: detect changed nodes (updatedAt > last sync time) → re-embed → upsert
- Filter: ONLY sync nodes where isCanonical = true
- Validate: Qdrant count == Postgres count WHERE isCanonical = true

Deliverable: vector search "quiet coffee shop in Austin" returns relevant hydrated nodes.

## Output
services/api/pipeline/qdrant_sync.py

## Zone
sync

## Dependencies
- M-008

## Priority
45

## Target Files
- services/api/pipeline/qdrant_sync.py

## Files
- services/api/embedding/service.py
- services/api/search/qdrant_client.py
- docs/plans/vertical-plans-v2.md
