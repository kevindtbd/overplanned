# Data Pipeline Track — Manifest

## Zones

### Zone: scraper-framework
Directory: services/api/scrapers
- services/api/scrapers/base.py

### Zone: scrapers
Directory: services/api/scrapers
- services/api/scrapers/blog_rss.py
- services/api/scrapers/atlas_obscura.py
- services/api/scrapers/foursquare.py
- services/api/scrapers/arctic_shift.py

### Zone: resolution
Directory: services/api/pipeline
**SUPER**
- services/api/pipeline/entity_resolution.py

### Zone: tagging
Directory: services/api/pipeline
- services/api/pipeline/vibe_extraction.py
- services/api/pipeline/rule_inference.py
- services/api/pipeline/convergence.py

### Zone: sync
Directory: services/api/pipeline
- services/api/pipeline/qdrant_sync.py

### Zone: orchestrator
Directory: services/api/pipeline
**SUPER**
- services/api/pipeline/city_seeder.py

### Zone: maintenance
Directory: services/api/pipeline
- services/api/pipeline/image_validation.py
- services/api/pipeline/content_purge.py

### Zone: tests
Directory: tests
- services/api/tests/pipeline/
