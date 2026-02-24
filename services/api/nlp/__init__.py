"""
NLP utilities for Overplanned.

Shared infrastructure for preference extraction from natural language text.
Used by:
  - ChatGPT conversation import (Wave D)
  - Onboarding freetext input (Phase 3.2)

No database access in this package — pure text-in / signals-out.
"""

from services.api.nlp.preference_extractor import (
    PreferenceSignal,
    extract_preferences,
    extract_preferences_rules,
    extract_preferences_llm,
)

__all__ = [
    "PreferenceSignal",
    "extract_preferences",
    "extract_preferences_rules",
    "extract_preferences_llm",
]
