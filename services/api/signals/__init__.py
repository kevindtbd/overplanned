"""
Overplanned signals package — V2 ML Pipeline.

Modules
-------
taxonomy            Signal hierarchy weights and polarity classification
ranking_logger      Fire-and-forget RankingEvent row writer
persona_snapshot    User persona dimension aggregator
subflow_tagger      Phase 1.2 — assigns a subflow context to BehavioralSignals
alteration_tagger   Phase 1.3 — detects itinerary-alteration patterns in sessions
off_plan_handler    Phase 1.4 — handles off-plan activity adds (mid-trip)
"""
