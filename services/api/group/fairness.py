"""
Fairness Engine — tracks and resolves preference debt across group members.

Core algorithm:
  For each vote on a slot:
    debt_delta[member] = member_preference_rank - group_choice_rank

  Where:
    - member_preference_rank:  How highly this member ranked the chosen activity
                               (1 = their top choice, higher = they preferred something else)
    - group_choice_rank:       The activity's rank in the group's merged ranking
                               (always 1 for the slot that was selected)

  A member accumulates positive debt when the group picks something they
  ranked lower than the group consensus.
  A member pays down debt when the group picks one of their top choices.

Fairness-weighted conflict resolution:
  When a slot is contested, the member with the highest cumulative debt gets
  their alternative preferences boosted when re-searching candidates.
  Boost weight = 1 / (1 + cumulative_debt)  -- inverse debt weighting
  Most-compromised member exerts the strongest pull on the next search.

Determinism guarantee:
  Given the same fairness_state and vote results, this module always
  produces the same output. No randomness, no external calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Scaling factor for debt accumulation. Keeps debt in a bounded range
# so one extreme vote doesn't permanently dominate.
_DEBT_SCALE = 1.0

# Maximum raw debt a member can accumulate (prevents runaway).
_MAX_DEBT = 10.0

# Minimum boost weight (prevents any member being completely ignored).
_MIN_BOOST_WEIGHT = 0.05


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MemberDebt:
    """Per-member fairness debt record."""
    member_id: str
    cumulative_debt: float = 0.0
    vote_count: int = 0
    compromise_count: int = 0  # votes where debt increased

    def to_dict(self) -> dict[str, Any]:
        return {
            "memberId": self.member_id,
            "cumulativeDebt": round(self.cumulative_debt, 4),
            "voteCount": self.vote_count,
            "compromiseCount": self.compromise_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MemberDebt":
        return cls(
            member_id=d["memberId"],
            cumulative_debt=d.get("cumulativeDebt", 0.0),
            vote_count=d.get("voteCount", 0),
            compromise_count=d.get("compromiseCount", 0),
        )


@dataclass
class FairnessState:
    """
    Complete fairness state for a trip.

    Serializable to/from Trip.fairnessState JSONB.
    """
    members: dict[str, MemberDebt] = field(default_factory=dict)
    total_votes: int = 0
    last_updated_slot: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "members": {mid: debt.to_dict() for mid, debt in self.members.items()},
            "totalVotes": self.total_votes,
            "lastUpdatedSlot": self.last_updated_slot,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "FairnessState":
        if not d:
            return cls()
        members = {}
        for mid, debt_data in d.get("members", {}).items():
            members[mid] = MemberDebt.from_dict(debt_data)
        return cls(
            members=members,
            total_votes=d.get("totalVotes", 0),
            last_updated_slot=d.get("lastUpdatedSlot"),
        )


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class FairnessEngine:
    """
    Computes and accumulates per-member fairness debt.

    Fully deterministic — no external calls, no randomness.
    Same inputs always produce same outputs.

    Usage:
        engine = FairnessEngine()

        # After each vote resolution:
        new_state = engine.record_vote(
            state=current_fairness_state,
            slot_id="slot-123",
            chosen_node_id="node-abc",
            member_preference_ranks={
                "user-1": 2,   # user-1 ranked this their 2nd choice
                "user-2": 1,   # user-2 ranked this their top choice
                "user-3": 4,   # user-3 had to compromise most
            },
            group_choice_rank=1,
        )

        # Before resolving a conflict:
        weights = engine.conflict_weights(state=new_state, member_ids=["user-1", "user-2"])
    """

    def record_vote(
        self,
        state: FairnessState,
        slot_id: str,
        chosen_node_id: str,
        member_preference_ranks: dict[str, int],
        group_choice_rank: int = 1,
    ) -> FairnessState:
        """
        Record a resolved vote and update member debt.

        Args:
            state:                    Current FairnessState (mutated copy returned).
            slot_id:                  ID of the ItinerarySlot just resolved.
            chosen_node_id:           ID of the ActivityNode that won the vote.
            member_preference_ranks:  { memberId -> rank this member gave chosen_node }
                                      Lower rank = member preferred this node.
                                      Rank 1 = member's top choice.
            group_choice_rank:        Rank of chosen_node in the group's merged ranking.
                                      Usually 1 (the group's top pick won).

        Returns:
            New FairnessState with updated debts.
        """
        # Work on a copy to keep the engine stateless/pure from caller's perspective
        new_state = FairnessState(
            members={
                mid: MemberDebt(
                    member_id=mid,
                    cumulative_debt=debt.cumulative_debt,
                    vote_count=debt.vote_count,
                    compromise_count=debt.compromise_count,
                )
                for mid, debt in state.members.items()
            },
            total_votes=state.total_votes,
            last_updated_slot=state.last_updated_slot,
        )

        for member_id, member_rank in member_preference_ranks.items():
            # Ensure member record exists
            if member_id not in new_state.members:
                new_state.members[member_id] = MemberDebt(member_id=member_id)

            debt_record = new_state.members[member_id]

            # debt_delta = how much this member had to compromise
            # Positive = member preferred something else (debt increases)
            # Negative = group picked member's top choice (debt decreases)
            debt_delta = (member_rank - group_choice_rank) * _DEBT_SCALE

            debt_record.cumulative_debt = max(
                -_MAX_DEBT,
                min(_MAX_DEBT, debt_record.cumulative_debt + debt_delta),
            )
            debt_record.vote_count += 1
            if debt_delta > 0:
                debt_record.compromise_count += 1

            logger.debug(
                "Fairness debt: member=%s slot=%s delta=%.2f total=%.2f",
                member_id,
                slot_id,
                debt_delta,
                debt_record.cumulative_debt,
            )

        new_state.total_votes += 1
        new_state.last_updated_slot = slot_id

        return new_state

    def conflict_weights(
        self,
        state: FairnessState,
        member_ids: list[str],
    ) -> dict[str, float]:
        """
        Compute conflict resolution weights for a contested slot.

        Members with higher cumulative debt (more compromised) get higher
        weight in the next alternative search. This gives under-served
        members more influence in resolving conflicts.

        Formula: weight[member] = 1 / (1 + max(0, cumulative_debt))
        Then normalized to sum = 1.0.

        Members with negative debt (they've been "winning") get the minimum
        weight floor to stay included.

        Args:
            state:       Current FairnessState.
            member_ids:  Members participating in the conflict vote.

        Returns:
            Normalized weight dict { memberId -> weight }, sum = 1.0.
        """
        if not member_ids:
            return {}

        raw_weights: dict[str, float] = {}
        for mid in member_ids:
            debt = state.members.get(mid)
            cumulative = debt.cumulative_debt if debt else 0.0
            # Higher debt = lower denominator = higher weight
            raw = 1.0 / (1.0 + max(0.0, cumulative))
            raw_weights[mid] = max(raw, _MIN_BOOST_WEIGHT)

        total = sum(raw_weights.values())
        return {mid: w / total for mid, w in raw_weights.items()}

    def most_compromised_member(
        self,
        state: FairnessState,
        member_ids: list[str],
    ) -> str | None:
        """
        Return the member_id with the highest cumulative debt.
        Returns None if member_ids is empty.
        """
        if not member_ids:
            return None

        return max(
            member_ids,
            key=lambda mid: state.members.get(mid, MemberDebt(mid)).cumulative_debt,
        )

    def fairness_summary(self, state: FairnessState) -> dict[str, Any]:
        """
        Return a human-readable summary of fairness state.
        Useful for logging and debugging.
        """
        debts_sorted = sorted(
            state.members.values(),
            key=lambda d: d.cumulative_debt,
            reverse=True,
        )
        return {
            "totalVotes": state.total_votes,
            "lastUpdatedSlot": state.last_updated_slot,
            "memberDebts": [d.to_dict() for d in debts_sorted],
            "mostCompromised": debts_sorted[0].member_id if debts_sorted else None,
            "leastCompromised": debts_sorted[-1].member_id if debts_sorted else None,
        }
