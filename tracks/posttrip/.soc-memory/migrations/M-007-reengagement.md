# M-007: Re-Engagement Loop

## Description
Push notification + email to bring users back after trip completion.

## Task
1. Next destination suggestion based on behavioral signals (Qdrant search with accumulated persona)
2. 24hr push: FCM setup, PushToken model, notification queue in Redis
3. 7-day email via Resend: trip memory + "Where next?"
4. Email: SPF/DKIM/DMARC, unsubscribe mechanism, rate limit 1 per 7 days
5. One-time-use login links for email deep links (15-min expiry)
6. No session tokens in push notification deep links

## Output
services/api/posttrip/reengagement.py

## Zone
engagement

## Dependencies
- M-006

## Priority
40

## Target Files
- services/api/posttrip/reengagement.py
- services/api/posttrip/push_service.py
- services/api/posttrip/email_service.py

## Files
- docs/plans/vertical-plans-v2.md
