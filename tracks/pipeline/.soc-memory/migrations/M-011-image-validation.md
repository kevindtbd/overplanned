# M-011: Image Validation Pipeline

## Description
Validate and curate images for ActivityNodes using a priority waterfall.

## Task
Create services/api/pipeline/image_validation.py:
- Image source waterfall (try in order):
  1. Unsplash (free API, high quality)
  2. Foursquare venue photos
  3. Google Places photos
  4. None (no image)

- Validation:
  - Cloud Vision API: quality check (blur, lighting)
  - Inappropriate content detection (SafeSearch)
  - Minimum resolution: 400x300

- Set imageUrl on ActivityNode on pass
- Set imageValidated: true

- Batch processing: process unvalidated nodes

Deliverable: nodes with images validated, bad images flagged.

## Output
services/api/pipeline/image_validation.py

## Zone
maintenance

## Dependencies
- M-010

## Priority
35

## Target Files
- services/api/pipeline/image_validation.py

## Files
- docs/plans/vertical-plans-v2.md
