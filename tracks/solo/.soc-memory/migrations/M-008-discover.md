# M-008: Discover/Explore Surface

## Description
Browse and discover activities. Cold start for new users, personalized for returning users.

## Task
Create apps/web/app/discover/:

1. Cold start (no behavioral signals yet):
   - Trending in city (highest convergenceScore nodes)
   - Editorial picks (highest authorityScore)
   - Category browsing

2. Returning user:
   - Qdrant vector search weighted by accumulated behavioral signals
   - Rules-based personalization at launch (NOT ML): boost categories user confirms, demote categories user skips
   - ML personalization comes later (Month 5+ BPR)

3. Shortlist: save activities for later consideration
   - Write BehavioralSignal: shortlist_add / shortlist_remove

4. Swipe deck (online only — offline descoped to v2):
   - Tinder-style card interface for quick browsing
   - Swipe right = interested, left = not interested
   - Write BehavioralSignal: swipe_right / swipe_left

5. Impression logging:
   - Every item shown writes RawEvent with position field
   - Critical for future position bias debiasing

## Output
apps/web/app/discover/page.tsx

## Zone
discover

## Dependencies
- M-007

## Priority
55

## Target Files
- apps/web/app/discover/page.tsx
- apps/web/app/discover/components/DiscoverFeed.tsx
- apps/web/app/discover/components/SwipeDeck.tsx
- apps/web/app/discover/components/Shortlist.tsx

## Files
- services/api/search/service.py
- docs/overplanned-design-v4.html
- docs/plans/vertical-plans-v2.md
