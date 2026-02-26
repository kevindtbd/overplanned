"""Cross-reference scorer for Pipeline D: merges D (LLM) + C (scrape/extract) signals."""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

C_WEIGHT_CONFLICT = 0.65
D_WEIGHT_CONFLICT = 0.35
C_WEIGHT_ALIGNED = 0.55
D_WEIGHT_ALIGNED = 0.45
TOURIST_CONFLICT_THRESHOLD = 0.25

D_CONF_WEIGHT = 0.4
C_CONF_WEIGHT = 0.6
AGREEMENT_BONUS = 0.15
AGREEMENT_JACCARD_THRESHOLD = 0.50
CONFLICT_PENALTY = 0.20

MAX_MERGED_TAGS = 8


@dataclass
class CSignal:
    convergence: float
    authority: float
    tourist_score: Optional[float]
    mention_count: int
    vibe_tags: list[str]
    has_signal: bool


@dataclass
class DSignal:
    tourist_score: Optional[float]
    research_confidence: float
    vibe_tags: list[str]
    source_amplification: bool
    knowledge_source: str


@dataclass
class CrossRefOutput:
    has_d_signal: bool = False
    has_c_signal: bool = False
    d_only: bool = False
    c_only: bool = False
    both_agree: bool = False
    both_conflict: bool = False
    tag_agreement_score: float = 0.0
    tourist_score_delta: Optional[float] = None
    signal_conflict: bool = False
    merged_vibe_tags: list[str] = field(default_factory=list)
    merged_tourist_score: Optional[float] = None
    merged_confidence: float = 0.0


def reconstruct_c_signal(node: dict, quality_signal_count: int) -> CSignal:
    convergence = node.get("convergenceScore") or 0.0
    authority = node.get("authorityScore") or 0.0
    tourist = node.get("tourist_score")
    source_count = node.get("sourceCount") or 0
    has_signal = convergence > 0 or authority > 0 or source_count > 0
    vibe_tags = node.get("_vibe_tags", [])
    return CSignal(convergence=convergence, authority=authority,
                   tourist_score=tourist, mention_count=quality_signal_count,
                   vibe_tags=vibe_tags, has_signal=has_signal)


def compute_tag_agreement(d_tags: list[str], c_tags: list[str]) -> float:
    d_set = set(d_tags)
    c_set = set(c_tags)
    if not d_set and not c_set:
        return 0.0
    if not d_set or not c_set:
        return 0.0
    return len(d_set & c_set) / len(d_set | c_set)


def merge_tourist_scores(c_score: Optional[float], d_score: Optional[float]) -> Optional[float]:
    if c_score is None and d_score is None:
        return None
    if c_score is None:
        return d_score
    if d_score is None:
        return c_score
    delta = abs(c_score - d_score)
    if delta > TOURIST_CONFLICT_THRESHOLD:
        return C_WEIGHT_CONFLICT * c_score + D_WEIGHT_CONFLICT * d_score
    else:
        return C_WEIGHT_ALIGNED * c_score + D_WEIGHT_ALIGNED * d_score


def compute_merged_confidence(
    d_conf: float, c_conf: float, tag_agreement: float,
    signal_conflict: bool = False,
) -> float:
    base = D_CONF_WEIGHT * d_conf + C_CONF_WEIGHT * c_conf
    if tag_agreement >= AGREEMENT_JACCARD_THRESHOLD:
        base += AGREEMENT_BONUS
    if signal_conflict:
        base -= CONFLICT_PENALTY
    return max(0.0, min(1.0, base))


def merge_vibe_tags(d_tags: list[str], c_tags: list[str]) -> list[str]:
    d_set = set(d_tags)
    c_set = set(c_tags)
    consensus = list(d_set & c_set)
    c_only = list(c_set - d_set)
    d_only = list(d_set - c_set)
    merged = consensus + c_only + d_only
    return merged[:MAX_MERGED_TAGS]


def score_cross_reference(c: CSignal, d: DSignal) -> CrossRefOutput:
    output = CrossRefOutput()
    output.has_c_signal = c.has_signal
    output.has_d_signal = d.research_confidence > 0 or bool(d.vibe_tags)

    if output.has_c_signal and output.has_d_signal:
        output.tag_agreement_score = compute_tag_agreement(d.vibe_tags, c.vibe_tags)
        if c.tourist_score is not None and d.tourist_score is not None:
            output.tourist_score_delta = abs(c.tourist_score - d.tourist_score)
        tag_conflict = output.tag_agreement_score < 0.20
        tourist_conflict = (output.tourist_score_delta or 0) > TOURIST_CONFLICT_THRESHOLD
        if tag_conflict or tourist_conflict:
            output.both_conflict = True
            output.signal_conflict = True
        else:
            output.both_agree = True
    elif output.has_d_signal and not output.has_c_signal:
        output.d_only = True
    elif output.has_c_signal and not output.has_d_signal:
        output.c_only = True

    output.merged_vibe_tags = merge_vibe_tags(d.vibe_tags, c.vibe_tags)
    output.merged_tourist_score = merge_tourist_scores(c.tourist_score, d.tourist_score)

    c_conf = c.convergence if c.has_signal else 0.0
    output.merged_confidence = compute_merged_confidence(
        d.research_confidence, c_conf, output.tag_agreement_score,
        signal_conflict=output.signal_conflict)

    return output
