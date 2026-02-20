# M-008: Convergence Scorer + Authority Scorer

## Description
Score ActivityNodes based on cross-source agreement (convergence) and source authority weighting.

## Task
Create services/api/pipeline/convergence.py:
- Convergence scoring:
  - Count unique sources per ActivityNode (via QualitySignal)
  - 3+ sources agreeing on same vibe tag → convergence boost
  - Formula: convergenceScore = min(unique_sources / 3.0, 1.0)

- Authority scoring:
  - Source authority weights (from source registry):
    - The Infatuation: 0.9, Atlas Obscura: 0.85, Foursquare: 0.7, Reddit (high upvotes): 0.6, Generic blog: 0.4
  - Formula: authorityScore = weighted average of source authorities for this node

- Update ActivityNode.convergenceScore and ActivityNode.authorityScore

Deliverable: multi-source nodes show higher convergence and authority than single-source.

## Output
services/api/pipeline/convergence.py

## Zone
tagging

## Dependencies
- M-006
- M-007

## Priority
50

## Target Files
- services/api/pipeline/convergence.py

## Files
- prisma/schema.prisma
- docs/plans/vertical-plans-v2.md
