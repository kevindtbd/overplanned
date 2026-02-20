"""
Mid-trip test suite (M-009).

Covers:
- Trigger detection: weather, closure, overrun, mood
- Cascade scope: same-day only, cross-day creates new PivotEvent
- Micro-stops: proximity calc, 200m radius, slot creation
- Prompt bar: Haiku parse, keyword fallback, injection prevention, MAX_PIVOT_DEPTH
- Trust: flag paths, signal writes, admin review queue
"""
