-- Tag Vocabulary Alignment Migration
-- Phase 2 of post-canary cleanup
--
-- A) Insert 36 LLM-only tags (44 LLM vocab minus 8 already in DB)
-- B) Insert 4 rule-inference extra tags
-- C) Soft-delete 25 DB-only tags (set isActive=false)
--
-- All operations are idempotent.

-- =========================================================================
-- A) Insert 36 LLM-only tags that are missing from the DB
-- =========================================================================

INSERT INTO vibe_tags (id, slug, name, category, "isActive", "sortOrder")
VALUES
  (gen_random_uuid(), 'slow-burn', 'slow-burn', 'general', true, 0),
  (gen_random_uuid(), 'immersive', 'immersive', 'general', true, 0),
  (gen_random_uuid(), 'iconic-worth-it', 'iconic-worth-it', 'general', true, 0),
  (gen_random_uuid(), 'locals-only', 'locals-only', 'general', true, 0),
  (gen_random_uuid(), 'destination-meal', 'destination-meal', 'general', true, 0),
  (gen_random_uuid(), 'street-food', 'street-food', 'general', true, 0),
  (gen_random_uuid(), 'local-institution', 'local-institution', 'general', true, 0),
  (gen_random_uuid(), 'drinks-forward', 'drinks-forward', 'general', true, 0),
  (gen_random_uuid(), 'physically-demanding', 'physically-demanding', 'general', true, 0),
  (gen_random_uuid(), 'easy-walk', 'easy-walk', 'general', true, 0),
  (gen_random_uuid(), 'nature-immersive', 'nature-immersive', 'general', true, 0),
  (gen_random_uuid(), 'urban-exploration', 'urban-exploration', 'general', true, 0),
  (gen_random_uuid(), 'deep-history', 'deep-history', 'general', true, 0),
  (gen_random_uuid(), 'contemporary-culture', 'contemporary-culture', 'general', true, 0),
  (gen_random_uuid(), 'people-watching', 'people-watching', 'general', true, 0),
  (gen_random_uuid(), 'early-morning', 'early-morning', 'general', true, 0),
  (gen_random_uuid(), 'group-friendly', 'group-friendly', 'general', true, 0),
  (gen_random_uuid(), 'social-scene', 'social-scene', 'general', true, 0),
  (gen_random_uuid(), 'low-interaction', 'low-interaction', 'general', true, 0),
  (gen_random_uuid(), 'intimate', 'intimate', 'general', true, 0),
  (gen_random_uuid(), 'offbeat', 'offbeat', 'general', true, 0),
  (gen_random_uuid(), 'scenic', 'scenic', 'general', true, 0),
  (gen_random_uuid(), 'interactive', 'interactive', 'general', true, 0),
  (gen_random_uuid(), 'participatory', 'participatory', 'general', true, 0),
  (gen_random_uuid(), 'queue-worthy', 'queue-worthy', 'general', true, 0),
  (gen_random_uuid(), 'book-ahead', 'book-ahead', 'general', true, 0),
  (gen_random_uuid(), 'no-frills', 'no-frills', 'general', true, 0),
  (gen_random_uuid(), 'repeat-worthy', 'repeat-worthy', 'general', true, 0),
  (gen_random_uuid(), 'once-in-a-trip', 'once-in-a-trip', 'general', true, 0),
  (gen_random_uuid(), 'underrated', 'underrated', 'general', true, 0),
  (gen_random_uuid(), 'time-sensitive', 'time-sensitive', 'general', true, 0),
  (gen_random_uuid(), 'locals-routine', 'locals-routine', 'general', true, 0),
  (gen_random_uuid(), 'budget-friendly', 'budget-friendly', 'general', true, 0),
  (gen_random_uuid(), 'mid-range', 'mid-range', 'general', true, 0),
  (gen_random_uuid(), 'splurge-worthy', 'splurge-worthy', 'general', true, 0),
  (gen_random_uuid(), 'free', 'free', 'general', true, 0)
ON CONFLICT (slug) DO NOTHING;

-- =========================================================================
-- B) Insert 4 rule-inference extra tags
-- =========================================================================

INSERT INTO vibe_tags (id, slug, name, category, "isActive", "sortOrder")
VALUES
  (gen_random_uuid(), 'food-focused', 'food-focused', 'general', true, 0),
  (gen_random_uuid(), 'browsing', 'browsing', 'general', true, 0),
  (gen_random_uuid(), 'sit-down', 'sit-down', 'general', true, 0),
  (gen_random_uuid(), 'fresh-air', 'fresh-air', 'general', true, 0)
ON CONFLICT (slug) DO NOTHING;

-- =========================================================================
-- C) Soft-delete 25 DB-only tags (set isActive = false)
-- =========================================================================

UPDATE vibe_tags
SET "isActive" = false
WHERE slug IN (
  'adventurous',
  'all-day',
  'artsy',
  'cozy',
  'cultural',
  'date-spot',
  'early-bird',
  'family-friendly',
  'fast-paced',
  'hole-in-the-wall',
  'local-favorite',
  'michelin-worthy',
  'minimalist',
  'modern',
  'outdoor-seating',
  'reservation-required',
  'romantic',
  'spectator',
  'spontaneous',
  'structured',
  'tourist-trap',
  'traditional',
  'weekday-best',
  'weekend-only',
  'work-friendly'
)
AND "isActive" = true;
