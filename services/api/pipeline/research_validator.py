"""Validation gate for Pipeline D LLM outputs."""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

OVER_CONFIDENCE_THRESHOLD = 0.85
OVER_CONFIDENCE_RATIO = 0.80
TAG_CONCENTRATION_RATIO = 0.70
TRAINING_PRIOR_RATIO = 0.60
SEMANTIC_DEVIATION_THRESHOLD = 0.30
SEMANTIC_DEVIATION_RATIO = 0.50

PASS_A_REQUIRED = {
    "neighborhood_character", "temporal_patterns", "peak_and_decline_flags",
    "source_amplification_flags", "divergence_signals", "synthesis_confidence",
}


@dataclass
class ValidationResult:
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.passed = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)


def validate_pass_a(synthesis: dict) -> ValidationResult:
    result = ValidationResult()
    missing = PASS_A_REQUIRED - set(synthesis.keys())
    if missing:
        result.add_error(f"Missing required fields: {missing}")
        return result

    conf = synthesis.get("synthesis_confidence", 0)
    if not (0.0 <= conf <= 1.0):
        result.add_error(f"synthesis_confidence {conf} out of range [0, 1]")

    return result


def validate_pass_b(
    venues: list[dict],
    valid_tags: set[str],
) -> ValidationResult:
    result = ValidationResult()
    if not venues:
        result.add_warning("Pass B returned 0 venues")
        return result

    invalid_tag_count = 0
    for v in venues:
        ts = v.get("tourist_score")
        if ts is not None and not (0.0 <= ts <= 1.0):
            result.add_error(f"tourist_score {ts} out of range for {v.get('venue_name')}")

        rc = v.get("research_confidence")
        if rc is not None and not (0.0 <= rc <= 1.0):
            result.add_error(f"research_confidence {rc} out of range for {v.get('venue_name')}")

        for tag in v.get("vibe_tags", []):
            if valid_tags and tag not in valid_tags:
                invalid_tag_count += 1

    if invalid_tag_count > 0:
        result.add_warning(f"{invalid_tag_count} invalid tags found (filtered)")

    high_conf = [v for v in venues if (v.get("research_confidence") or 0) > OVER_CONFIDENCE_THRESHOLD]
    if len(high_conf) / len(venues) > OVER_CONFIDENCE_RATIO:
        result.add_warning(f"Over-confidence: {len(high_conf)}/{len(venues)} venues above {OVER_CONFIDENCE_THRESHOLD}")

    tag_counts: dict[str, int] = {}
    for v in venues:
        for tag in v.get("vibe_tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    for tag, count in tag_counts.items():
        if count / len(venues) > TAG_CONCENTRATION_RATIO:
            result.add_warning(f"Tag concentration: '{tag}' on {count}/{len(venues)} venues")

    tp_count = sum(1 for v in venues if v.get("knowledge_source") == "training_prior")
    if tp_count / len(venues) > TRAINING_PRIOR_RATIO:
        result.add_warning(f"training_prior heavy: {tp_count}/{len(venues)} venues rely only on training data")

    return result


def validate_full(
    pass_a: dict,
    venues: list[dict],
    valid_tags: set[str],
    c_baseline_median: Optional[float] = None,
) -> ValidationResult:
    a_result = validate_pass_a(pass_a)
    b_result = validate_pass_b(venues, valid_tags)

    combined = ValidationResult()
    combined.errors = a_result.errors + b_result.errors
    combined.warnings = a_result.warnings + b_result.warnings
    combined.passed = a_result.passed and b_result.passed

    if c_baseline_median is not None and venues:
        low_count = sum(1 for v in venues
                        if (v.get("research_confidence") or 0) < c_baseline_median - SEMANTIC_DEVIATION_THRESHOLD)
        if low_count / len(venues) > SEMANTIC_DEVIATION_RATIO:
            combined.add_warning(
                f"Semantic validation: {low_count}/{len(venues)} venues score >{SEMANTIC_DEVIATION_THRESHOLD} "
                f"below C baseline median ({c_baseline_median:.2f}). Possible injection artifact.")

    return combined
