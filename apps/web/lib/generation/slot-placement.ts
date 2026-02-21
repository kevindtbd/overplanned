import type { ScoredNode, PlacedSlot, PersonaSeed } from "./types";
import { PACE_SLOTS_PER_DAY, MORNING_START_HOUR, TEMPLATE_WEIGHTS } from "./types";

// Category → preferred time of day (hour, 24h format)
const CATEGORY_TIME_PREFERENCE: Record<string, "morning" | "afternoon" | "evening" | "meal"> = {
  dining: "meal",
  drinks: "evening",
  culture: "morning",
  outdoors: "morning",
  active: "morning",
  entertainment: "afternoon",
  shopping: "afternoon",
  experience: "afternoon",
  nightlife: "evening",
  group_activity: "afternoon",
  wellness: "morning",
};

// Category → SlotType mapping
function categoryToSlotType(category: string): "anchor" | "flex" | "meal" {
  switch (category) {
    case "dining": return "meal";
    case "drinks":
    case "nightlife": return "flex";
    default: return "anchor";
  }
}

// Slot duration heuristics by category (minutes)
const CATEGORY_DURATION: Record<string, number> = {
  dining: 75,
  drinks: 60,
  culture: 120,
  outdoors: 120,
  active: 150,
  entertainment: 120,
  shopping: 90,
  experience: 120,
  nightlife: 120,
  group_activity: 150,
  wellness: 90,
};

interface TimeSlotTemplate {
  label: string;
  hourOffset: number;  // hours after morning start
  preferredCategory: "morning" | "afternoon" | "evening" | "meal";
}

// Slot templates relative to morning start time
function getDayTemplate(slotsPerDay: number): TimeSlotTemplate[] {
  if (slotsPerDay >= 6) {
    return [
      { label: "morning",    hourOffset: 0,    preferredCategory: "morning" },
      { label: "lunch",      hourOffset: 2.5,  preferredCategory: "meal" },
      { label: "afternoon1", hourOffset: 4.5,  preferredCategory: "afternoon" },
      { label: "afternoon2", hourOffset: 6.5,  preferredCategory: "afternoon" },
      { label: "dinner",     hourOffset: 9,    preferredCategory: "meal" },
      { label: "evening",    hourOffset: 11,   preferredCategory: "evening" },
    ];
  }
  if (slotsPerDay >= 4) {
    return [
      { label: "morning",   hourOffset: 0,   preferredCategory: "morning" },
      { label: "lunch",     hourOffset: 3,   preferredCategory: "meal" },
      { label: "afternoon", hourOffset: 5.5, preferredCategory: "afternoon" },
      { label: "dinner",    hourOffset: 8.5, preferredCategory: "meal" },
    ];
  }
  if (slotsPerDay >= 3) {
    return [
      { label: "brunch",    hourOffset: 1,   preferredCategory: "meal" },
      { label: "afternoon", hourOffset: 4,   preferredCategory: "afternoon" },
      { label: "dinner",    hourOffset: 8,   preferredCategory: "meal" },
    ];
  }
  // 2 slots
  return [
    { label: "activity", hourOffset: 1.5, preferredCategory: "morning" },
    { label: "dinner",   hourOffset: 8,   preferredCategory: "meal" },
  ];
}

/**
 * Place scored + selected nodes into day/time slots.
 */
export function placeSlots(
  selectedNodes: ScoredNode[],
  totalDays: number,
  personaSeed: PersonaSeed,
  tripStartDate: Date,
): PlacedSlot[] {
  const templateConfig = personaSeed.template
    ? TEMPLATE_WEIGHTS[personaSeed.template] ?? null
    : null;

  const baseSlotsPerDay = PACE_SLOTS_PER_DAY[personaSeed.pace];
  const paceModifier = templateConfig?.paceModifier ?? 0;
  const slotsPerDay = Math.max(2, Math.min(7, baseSlotsPerDay + paceModifier));

  // Trip-length adjustment
  let effectiveSlotsPerDay = slotsPerDay;
  if (totalDays > 7 && personaSeed.pace !== "packed") {
    // Long trips: slightly reduce density to avoid fatigue
    effectiveSlotsPerDay = Math.max(2, slotsPerDay - 1);
  }

  const morningStart = MORNING_START_HOUR[personaSeed.morningPreference];
  const dayTemplate = getDayTemplate(effectiveSlotsPerDay);

  // Bucket nodes by time preference
  const mealNodes: ScoredNode[] = [];
  const morningNodes: ScoredNode[] = [];
  const afternoonNodes: ScoredNode[] = [];
  const eveningNodes: ScoredNode[] = [];

  for (const node of selectedNodes) {
    const timePref = CATEGORY_TIME_PREFERENCE[node.category] ?? "afternoon";
    switch (timePref) {
      case "meal": mealNodes.push(node); break;
      case "morning": morningNodes.push(node); break;
      case "evening": eveningNodes.push(node); break;
      default: afternoonNodes.push(node); break;
    }
  }

  const placed: PlacedSlot[] = [];
  const usedNodeIds = new Set<string>();

  for (let day = 1; day <= totalDays; day++) {
    const daySlots = dayTemplate.slice(0, effectiveSlotsPerDay);

    for (let slotIdx = 0; slotIdx < daySlots.length; slotIdx++) {
      const template = daySlots[slotIdx];

      // Pick best available node for this time slot
      let node: ScoredNode | undefined;
      const preferred = template.preferredCategory;

      // Try preferred bucket first, fall back to others
      const bucketOrder: ScoredNode[][] =
        preferred === "meal" ? [mealNodes, morningNodes, afternoonNodes, eveningNodes] :
        preferred === "morning" ? [morningNodes, mealNodes, afternoonNodes, eveningNodes] :
        preferred === "evening" ? [eveningNodes, afternoonNodes, mealNodes, morningNodes] :
        [afternoonNodes, morningNodes, eveningNodes, mealNodes];

      for (const bucket of bucketOrder) {
        const idx = bucket.findIndex(n => !usedNodeIds.has(n.nodeId));
        if (idx !== -1) {
          node = bucket.splice(idx, 1)[0];
          break;
        }
      }

      if (!node) continue; // ran out of nodes

      usedNodeIds.add(node.nodeId);

      const hourOffset = morningStart + template.hourOffset;
      const startHour = Math.floor(hourOffset);
      const startMinute = Math.round((hourOffset - startHour) * 60);
      const duration = CATEGORY_DURATION[node.category] ?? 90;

      // Build actual datetime
      const startTime = new Date(tripStartDate);
      startTime.setDate(startTime.getDate() + (day - 1));
      startTime.setHours(startHour, startMinute, 0, 0);

      const endTime = new Date(startTime.getTime() + duration * 60 * 1000);

      placed.push({
        nodeId: node.nodeId,
        name: node.name,
        category: node.category,
        dayNumber: day,
        sortOrder: slotIdx + 1,
        slotType: categoryToSlotType(node.category),
        startTime,
        endTime,
        durationMinutes: duration,
      });
    }
  }

  return placed;
}
