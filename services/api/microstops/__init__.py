"""
Micro-stops subsystem — proximity-based suggestions during transit slots.

A micro-stop is a lightweight ItinerarySlot (slotType=flex, 15-30 min)
inserted when the system detects interesting ActivityNodes within 200m of
the transit path between two anchor/meal slots.

Public API:
    from services.api.microstops.service import MicroStopService
    from services.api.microstops.spatial import find_nodes_along_path
"""
