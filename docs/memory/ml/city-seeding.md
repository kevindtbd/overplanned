# ML / City Seeding

## Strategy
- See `docs/overplanned-city-seeding-strategy.md` for full spec
- 13 launch cities
- Pipeline: scrape all sources -> entity resolution -> dedup -> vibe tag -> embed -> load

## Seeded Cities (Current)
- Mexico City: 73 activity nodes
- New York: 72 activity nodes
- Tokyo: 20 activity nodes

## Entity Resolution
- Canonical name + dedup chain + ActivityAlias
- Content hash dedup (SHA256)
- Cross-reference convergence scorer

## Learnings
- (space for future compound learnings)
