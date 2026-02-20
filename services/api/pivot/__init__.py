"""
Pivot subsystem — trigger detection, cascade evaluation, prompt parsing.

Trigger types (mirrors PivotTrigger enum in schema):
  weather_change  — rain/storm against an outdoor-category slot
  venue_closed    — Google Places hours show venue is closed right now
  time_overrun    — slot endTime has passed without slot completion
  user_mood       — explicit "not feeling it" signal from the user
  user_request    — direct user-initiated swap request

MAX_PIVOT_DEPTH = 1: pivot alternatives are never themselves re-pivoted.
"""
