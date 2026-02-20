# M-010: Embedding Infrastructure

## Description
Set up nomic-embed-text-v1.5 for local embedding generation. Both batch (pipeline) and single-query (search) modes.

## Task
1. Install sentence-transformers in services/api/requirements.txt

2. Create services/api/embedding/service.py — EmbeddingService class:
   - Model: nomic-embed-text-v1.5 (768 dimensions)
   - Lazy load model on first use (~270MB download)
   - embed_single(text: str) → List[float] (768-dim vector)
   - embed_batch(texts: List[str], batch_size: int = 32) → List[List[float]]
   - Normalize vectors (L2 norm) before return

3. Batch embedding endpoint: POST /embed/batch
   - Accepts list of texts
   - Returns list of 768-dim vectors
   - Max 100 texts per request

4. Single query embedding (used by ActivitySearchService):
   - Fast path for search queries
   - Integrate with M-009's search service

5. Register model in ModelRegistry:
   - type: "embedding"
   - name: "nomic-embed-text-v1.5"
   - version: "1.5"
   - stage: "production"

Deliverable: embed single text → 768-dim vector. Batch of 100 texts embeds under 5s.

## Output
services/api/embedding/service.py

## Zone
embedding

## Dependencies
- M-006

## Priority
60

## Target Files
- services/api/embedding/service.py
- services/api/routers/embed.py

## Files
- services/api/main.py
- services/api/requirements.txt
- docs/plans/vertical-plans-v2.md
