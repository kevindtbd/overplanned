"""
Phase 6.5 -- Arbitration Layer

Deterministic rule-based arbitration between ML ranker and LLM ranker.
Runs both in parallel, picks winner based on context. No ML here -- pure
business logic and logging.

CPU-only: pure numpy for agreement scoring, no heavy frameworks.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums & Data Types
# ---------------------------------------------------------------------------

class ArbitrationRule(Enum):
    ML_WINS = "ml_wins"
    LLM_WINS = "llm_wins"
    BLEND = "blend"
    LLM_COLD = "llm_cold"
    ML_EXPLORE = "ml_explore"


@dataclass
class ArbitrationContext:
    """All signals needed to make an arbitration decision."""

    user_signal_count: int
    trip_count: int
    ml_confidence: float
    ml_rankings: list[str]
    llm_rankings: list[str]
    persona_vibes: list[str] = field(default_factory=list)
    exploration_budget_remaining: int = 0


@dataclass
class ArbitrationDecision:
    """Output of the arbitration process."""

    rule_fired: ArbitrationRule
    served_rankings: list[str]
    served_source: str  # "ml" | "llm" | "blend"
    agreement_score: float


# ---------------------------------------------------------------------------
# Arbitrator
# ---------------------------------------------------------------------------

class Arbitrator:
    """
    Deterministic rule-based arbiter between ML and LLM ranking outputs.

    Rule priority (first match wins):
      1. trip_count == 0               -> LLM_COLD
      2. user_signal_count < 10        -> LLM_WINS
      3. exploration_budget > 0        -> ML_EXPLORE (10-15% exploration)
      4. ml_confidence > 0.7 AND
         agreement_score > 0.4         -> ML_WINS
      5. ml_confidence > 0.5           -> BLEND
      6. default                       -> LLM_WINS
    """

    @staticmethod
    def compute_agreement_score(
        ml_rankings: list[str],
        llm_rankings: list[str],
        k: int = 5,
    ) -> float:
        """
        Overlap@k between ML and LLM rankings.

        Returns fraction of top-k items that appear in both lists.
        """
        if not ml_rankings or not llm_rankings:
            return 0.0

        ml_top = set(ml_rankings[:k])
        llm_top = set(llm_rankings[:k])

        if not ml_top or not llm_top:
            return 0.0

        overlap = len(ml_top & llm_top)
        return overlap / k

    @staticmethod
    def _blend_rankings(
        ml_rankings: list[str],
        llm_rankings: list[str],
    ) -> list[str]:
        """
        Interleave ML and LLM rankings, deduplicating.

        Pattern: [ml[0], llm[0], ml[1], llm[1], ...]
        """
        seen: set[str] = set()
        blended: list[str] = []
        max_len = max(len(ml_rankings), len(llm_rankings))

        for i in range(max_len):
            if i < len(ml_rankings) and ml_rankings[i] not in seen:
                blended.append(ml_rankings[i])
                seen.add(ml_rankings[i])
            if i < len(llm_rankings) and llm_rankings[i] not in seen:
                blended.append(llm_rankings[i])
                seen.add(llm_rankings[i])

        return blended

    def arbitrate(self, context: ArbitrationContext) -> ArbitrationDecision:
        """
        Apply priority rules to decide which ranker to serve.

        Args:
            context: full arbitration context

        Returns:
            ArbitrationDecision with rule_fired, served_rankings, etc.
        """
        agreement = self.compute_agreement_score(
            context.ml_rankings, context.llm_rankings
        )

        # Rule 1: brand new user, zero trips
        if context.trip_count == 0:
            return ArbitrationDecision(
                rule_fired=ArbitrationRule.LLM_COLD,
                served_rankings=context.llm_rankings,
                served_source="llm",
                agreement_score=agreement,
            )

        # Rule 2: warm but not enough signal
        if context.user_signal_count < 10:
            return ArbitrationDecision(
                rule_fired=ArbitrationRule.LLM_WINS,
                served_rankings=context.llm_rankings,
                served_source="llm",
                agreement_score=agreement,
            )

        # Rule 3: exploration budget
        if context.exploration_budget_remaining > 0:
            return ArbitrationDecision(
                rule_fired=ArbitrationRule.ML_EXPLORE,
                served_rankings=context.ml_rankings,
                served_source="ml",
                agreement_score=agreement,
            )

        # Rule 4: high ML confidence + reasonable agreement
        if context.ml_confidence > 0.7 and agreement > 0.4:
            return ArbitrationDecision(
                rule_fired=ArbitrationRule.ML_WINS,
                served_rankings=context.ml_rankings,
                served_source="ml",
                agreement_score=agreement,
            )

        # Rule 5: moderate ML confidence -> blend
        if context.ml_confidence > 0.5:
            blended = self._blend_rankings(
                context.ml_rankings, context.llm_rankings
            )
            return ArbitrationDecision(
                rule_fired=ArbitrationRule.BLEND,
                served_rankings=blended,
                served_source="blend",
                agreement_score=agreement,
            )

        # Rule 6: default -> LLM
        return ArbitrationDecision(
            rule_fired=ArbitrationRule.LLM_WINS,
            served_rankings=context.llm_rankings,
            served_source="llm",
            agreement_score=agreement,
        )

    async def log_arbitration_event(
        self,
        pool: Any,
        user_id: str,
        trip_id: str,
        decision: ArbitrationDecision,
        context: ArbitrationContext | None = None,
    ) -> str:
        """
        Write arbitration decision to the ArbitrationEvent table.

        Args:
            pool: asyncpg connection pool
            user_id: user UUID
            trip_id: trip UUID
            decision: the arbitration result
            context: optional context for snapshot

        Returns:
            The event row ID
        """
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        ml_top3 = decision.served_rankings[:3] if decision.served_source == "ml" else (
            context.ml_rankings[:3] if context else []
        )
        llm_top3 = decision.served_rankings[:3] if decision.served_source == "llm" else (
            context.llm_rankings[:3] if context else []
        )

        context_snapshot = {}
        if context:
            context_snapshot = {
                "user_signal_count": context.user_signal_count,
                "trip_count": context.trip_count,
                "ml_confidence": context.ml_confidence,
                "persona_vibes": context.persona_vibes,
                "exploration_budget_remaining": context.exploration_budget_remaining,
            }

        await pool.execute(
            """
            INSERT INTO arbitration_events (
                "id", "userId", "tripId", "mlTop3", "llmTop3",
                "arbitrationRule", "servedSource", "accepted",
                "agreementScore", "contextSnapshot", "createdAt"
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
            """,
            event_id,
            user_id,
            trip_id,
            ml_top3,
            llm_top3,
            decision.rule_fired.value,
            decision.served_source,
            None,  # accepted -- filled later when user responds
            decision.agreement_score,
            json.dumps(context_snapshot),
            now,
        )
        return event_id
