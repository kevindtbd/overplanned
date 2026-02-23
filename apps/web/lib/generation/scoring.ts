import type { ScoredNode, PersonaSeed, TemplateConfig } from "./types";
import { TEMPLATE_WEIGHTS, DEFAULT_WEIGHTS } from "./types";

interface ActivityNodeRow {
  id: string;
  name: string;
  category: string;
  latitude: number;
  longitude: number;
  neighborhood: string | null;
  descriptionShort: string | null;
  priceLevel: number | null;
  authorityScore: number | null;
  vibeTags: { vibeTag: { slug: string; name: string }; score: number }[];
}

export function scoreNodes(
  nodes: ActivityNodeRow[],
  personaSeed: PersonaSeed,
): ScoredNode[] {
  const templateConfig: TemplateConfig | null = personaSeed.template
    ? TEMPLATE_WEIGHTS[personaSeed.template] ?? null
    : null;

  const categoryWeights = templateConfig?.weights ?? DEFAULT_WEIGHTS;

  // Convert food preferences + vibe preferences to a combined lowercase set for matching
  const foodPrefs = personaSeed.foodPreferences.map(f => f.toLowerCase());
  const vibePrefs = (personaSeed.vibePreferences ?? []).map(v => v.toLowerCase());
  const prefSet = new Set([...foodPrefs, ...vibePrefs]);

  const scored: ScoredNode[] = nodes.map((node) => {
    let score = 0;

    // 1. Template category weight (0 - 0.40)
    const catWeight = categoryWeights[node.category] ?? 0.05;
    score += catWeight * 0.4 / 0.4; // normalize: max category weight (~0.4) maps to 0.4 score

    // 2. Vibe tag overlap (0 - 0.30)
    const nodeTags = node.vibeTags.map(vt => vt.vibeTag.slug.toLowerCase());
    const nodeTagNames = node.vibeTags.map(vt => vt.vibeTag.name.toLowerCase());
    const allNodeTags = new Set([...nodeTags, ...nodeTagNames]);
    let tagOverlap = 0;
    for (const pref of prefSet) {
      if (allNodeTags.has(pref)) tagOverlap++;
      // Also check partial match (e.g. "ramen" matches "ramen-shops")
      for (const tag of allNodeTags) {
        if (tag.includes(pref) || pref.includes(tag)) {
          tagOverlap += 0.5;
          break;
        }
      }
    }
    score += Math.min(tagOverlap / Math.max(prefSet.size, 1), 1) * 0.30;

    // 3. Authority score (0 - 0.15)
    if (node.authorityScore != null) {
      score += Math.min(node.authorityScore, 1) * 0.15;
    } else {
      score += 0.075; // neutral if no authority data
    }

    // 4. Base diversity bonus will be applied during selection, not scoring
    // Add small random jitter to break ties (0 - 0.05)
    score += Math.random() * 0.05;

    return {
      nodeId: node.id,
      name: node.name,
      category: node.category,
      latitude: node.latitude,
      longitude: node.longitude,
      neighborhood: node.neighborhood,
      descriptionShort: node.descriptionShort,
      priceLevel: node.priceLevel,
      authorityScore: node.authorityScore,
      vibeTagSlugs: nodeTags,
      score,
    };
  });

  // Sort descending by score
  scored.sort((a, b) => b.score - a.score);

  return scored;
}

/**
 * Select nodes for the itinerary with diversity constraints.
 * Ensures we don't stack too many of the same category.
 */
export function selectNodes(
  scoredNodes: ScoredNode[],
  totalSlots: number,
): ScoredNode[] {
  const selected: ScoredNode[] = [];
  const categoryCount: Record<string, number> = {};
  const maxPerCategory = Math.ceil(totalSlots / 3); // no category > 1/3 of slots

  for (const node of scoredNodes) {
    if (selected.length >= totalSlots) break;

    const cat = node.category;
    const currentCount = categoryCount[cat] ?? 0;

    if (currentCount >= maxPerCategory) continue;

    selected.push(node);
    categoryCount[cat] = currentCount + 1;
  }

  return selected;
}
