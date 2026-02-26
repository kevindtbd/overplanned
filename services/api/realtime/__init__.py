"""
Real-time persona layer — two Redis-backed tiers for within-trip learning.

L1 — SessionPersonaDelta
    Ephemeral per-session accumulator. Accumulates behavioral signal
    adjustments for a single app open (~30 min idle TTL). Never writes
    back to the PersonaDimension DB table directly.

L2 — TripPersonaCache
    Persists across app opens for the full duration of a single trip.
    Session deltas merge into this cache at session end. Absolute TTL
    set to trip.end_date + 48 hours via EXPIREAT.

Usage:
    from services.api.realtime import SessionPersonaDelta, TripPersonaCache
"""

from __future__ import annotations

from services.api.realtime.session_delta import SessionPersonaDelta
from services.api.realtime.trip_cache import TripPersonaCache

__all__ = ["SessionPersonaDelta", "TripPersonaCache"]
