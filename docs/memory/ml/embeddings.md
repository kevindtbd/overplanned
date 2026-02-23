# ML / Embeddings & Vector Search

## Stack
- Qdrant (Docker locally, Cloud Run in prod)
- nomic-embed-text-v1.5 (768 dim, Apache 2.0, local inference)

## Architecture
- World Knowledge layer stored in Qdrant
- Activity nodes embedded with vibe tags + descriptions
- Qdrant search feeds generation engine

## City Seeding
- 13 launch cities planned
- Seeded: Mexico City (73 nodes), New York (72), Tokyo (20)
- Seeding pipeline: scrape -> entity resolution -> vibe tagging -> embedding -> Qdrant load

## Learnings
- (space for future compound learnings)
