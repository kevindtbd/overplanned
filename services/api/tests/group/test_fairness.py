"""
Fairness engine tests — M-005.

Validates:
  - debt_delta calculation per vote
  - cumulative debt accumulation
  - conflict_weights inverse debt weighting
  - most_compromised_member selection
  - determinism: same input -> same output
  - debt clamping at MAX_DEBT boundary
"""

from __future__ import annotations

import pytest

from services.api.group.fairness import (
    FairnessEngine,
    FairnessState,
    MemberDebt,
    _MAX_DEBT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> FairnessEngine:
    return FairnessEngine()


@pytest.fixture
def three_members() -> list[str]:
    return ["user-alice", "user-bob", "user-charlie"]


@pytest.fixture
def empty_state(three_members) -> FairnessState:
    state = FairnessState()
    for mid in three_members:
        state.members[mid] = MemberDebt(member_id=mid)
    return state


# ---------------------------------------------------------------------------
# Debt delta calculation
# ---------------------------------------------------------------------------

class TestDebtDelta:
    """debt_delta = member_preference_rank - group_choice_rank"""

    def test_zero_debt_when_member_top_choice_wins(self, engine, empty_state):
        """Member's top pick wins -> delta = 1 - 1 = 0."""
        new_state = engine.record_vote(
            state=empty_state,
            slot_id="slot-001",
            chosen_node_id="node-A",
            member_preference_ranks={"user-alice": 1},
            group_choice_rank=1,
        )
        debt = new_state.members["user-alice"].cumulative_debt
        assert debt == 0.0, f"Expected 0.0, got {debt}"

    def test_positive_debt_when_member_compromises(self, engine, empty_state):
        """Member ranked it 3rd, group picked it 1st -> delta = 2."""
        new_state = engine.record_vote(
            state=empty_state,
            slot_id="slot-002",
            chosen_node_id="node-B",
            member_preference_ranks={"user-alice": 3},
            group_choice_rank=1,
        )
        debt = new_state.members["user-alice"].cumulative_debt
        assert debt == pytest.approx(2.0), f"Expected 2.0, got {debt}"

    def test_negative_debt_when_member_wins_vs_group(self, engine, empty_state):
        """Member's top pick (rank 1) beats group rank of 3 -> delta = -2."""
        new_state = engine.record_vote(
            state=empty_state,
            slot_id="slot-003",
            chosen_node_id="node-C",
            member_preference_ranks={"user-alice": 1},
            group_choice_rank=3,
        )
        debt = new_state.members["user-alice"].cumulative_debt
        assert debt == pytest.approx(-2.0), f"Expected -2.0, got {debt}"

    def test_multi_member_vote_records_all_deltas(self, engine, empty_state):
        """Different member ranks produce different deltas in single vote."""
        new_state = engine.record_vote(
            state=empty_state,
            slot_id="slot-004",
            chosen_node_id="node-D",
            member_preference_ranks={
                "user-alice": 1,   # delta 0
                "user-bob": 2,     # delta 1
                "user-charlie": 5, # delta 4
            },
            group_choice_rank=1,
        )
        assert new_state.members["user-alice"].cumulative_debt == pytest.approx(0.0)
        assert new_state.members["user-bob"].cumulative_debt == pytest.approx(1.0)
        assert new_state.members["user-charlie"].cumulative_debt == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# Cumulative accumulation
# ---------------------------------------------------------------------------

class TestCumulativeDebt:
    """Debt accumulates across multiple votes."""

    def test_debt_accumulates_over_votes(self, engine, empty_state):
        """Three consecutive compromises accumulate."""
        state = empty_state
        for _ in range(3):
            state = engine.record_vote(
                state=state,
                slot_id=f"slot-{_}",
                chosen_node_id="node-X",
                member_preference_ranks={"user-alice": 3},
                group_choice_rank=1,
            )
        # Each vote adds 2.0 debt -> 6.0 total
        assert state.members["user-alice"].cumulative_debt == pytest.approx(6.0)

    def test_vote_count_increments(self, engine, empty_state):
        """total_votes increments by 1 per record_vote call."""
        state = empty_state
        assert state.total_votes == 0
        state = engine.record_vote(
            state=state, slot_id="s1", chosen_node_id="n1",
            member_preference_ranks={"user-alice": 1},
        )
        assert state.total_votes == 1
        state = engine.record_vote(
            state=state, slot_id="s2", chosen_node_id="n2",
            member_preference_ranks={"user-alice": 2},
        )
        assert state.total_votes == 2

    def test_compromise_count_increments_only_on_positive_delta(self, engine, empty_state):
        """compromise_count only increases when delta > 0."""
        state = engine.record_vote(
            state=empty_state,
            slot_id="s1",
            chosen_node_id="n1",
            member_preference_ranks={"user-alice": 1},  # delta=0
        )
        assert state.members["user-alice"].compromise_count == 0

        state = engine.record_vote(
            state=state,
            slot_id="s2",
            chosen_node_id="n2",
            member_preference_ranks={"user-alice": 3},  # delta=2
        )
        assert state.members["user-alice"].compromise_count == 1

    def test_debt_clamps_at_max(self, engine, empty_state):
        """Debt never exceeds _MAX_DEBT."""
        state = empty_state
        # Add huge rank delta
        state = engine.record_vote(
            state=state,
            slot_id="s1",
            chosen_node_id="n1",
            member_preference_ranks={"user-alice": 100},
            group_choice_rank=1,
        )
        assert state.members["user-alice"].cumulative_debt <= _MAX_DEBT

    def test_debt_clamps_at_min(self, engine, empty_state):
        """Debt never goes below -_MAX_DEBT."""
        state = empty_state
        state = engine.record_vote(
            state=state,
            slot_id="s1",
            chosen_node_id="n1",
            member_preference_ranks={"user-alice": 1},
            group_choice_rank=100,
        )
        assert state.members["user-alice"].cumulative_debt >= -_MAX_DEBT


# ---------------------------------------------------------------------------
# Conflict weights
# ---------------------------------------------------------------------------

class TestConflictWeights:
    """Most-compromised member gets highest weight in conflict resolution."""

    def test_weights_sum_to_one(self, engine, empty_state):
        """Weights are normalized and sum to 1.0."""
        weights = engine.conflict_weights(empty_state, ["user-alice", "user-bob"])
        total = sum(weights.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_higher_debt_member_gets_higher_weight(self, engine, empty_state):
        """Alice has more debt -> she should outweigh Bob in conflict resolution."""
        state = engine.record_vote(
            state=empty_state,
            slot_id="s1",
            chosen_node_id="n1",
            member_preference_ranks={
                "user-alice": 5,  # large compromise
                "user-bob": 1,    # happy
            },
        )
        weights = engine.conflict_weights(state, ["user-alice", "user-bob"])
        assert weights["user-alice"] > weights["user-bob"], (
            "More-compromised member must have higher conflict weight"
        )

    def test_equal_debt_means_equal_weights(self, engine):
        """Members with identical debt get identical weights."""
        state = FairnessState()
        state.members["u1"] = MemberDebt(member_id="u1", cumulative_debt=2.0)
        state.members["u2"] = MemberDebt(member_id="u2", cumulative_debt=2.0)
        weights = engine.conflict_weights(state, ["u1", "u2"])
        assert weights["u1"] == pytest.approx(weights["u2"], abs=1e-9)

    def test_negative_debt_member_gets_min_floor(self, engine):
        """Member with negative debt gets at least MIN_BOOST_WEIGHT."""
        state = FairnessState()
        state.members["u1"] = MemberDebt(member_id="u1", cumulative_debt=-5.0)
        state.members["u2"] = MemberDebt(member_id="u2", cumulative_debt=0.0)
        weights = engine.conflict_weights(state, ["u1", "u2"])
        assert weights["u1"] > 0.0
        assert weights["u2"] > 0.0


# ---------------------------------------------------------------------------
# Most compromised member
# ---------------------------------------------------------------------------

class TestMostCompromisedMember:
    """most_compromised_member returns member with highest cumulative debt."""

    def test_returns_highest_debt_member(self, engine):
        state = FairnessState()
        state.members["a"] = MemberDebt(member_id="a", cumulative_debt=1.0)
        state.members["b"] = MemberDebt(member_id="b", cumulative_debt=5.0)
        state.members["c"] = MemberDebt(member_id="c", cumulative_debt=2.0)
        result = engine.most_compromised_member(state, ["a", "b", "c"])
        assert result == "b"

    def test_returns_none_for_empty_members(self, engine, empty_state):
        result = engine.most_compromised_member(empty_state, [])
        assert result is None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Same input always produces the same output."""

    def test_same_votes_same_state(self, engine, empty_state):
        """Applying identical votes produces identical states."""
        votes = [
            ("s1", "n1", {"user-alice": 2, "user-bob": 1}),
            ("s2", "n2", {"user-alice": 1, "user-bob": 3}),
            ("s3", "n3", {"user-alice": 4, "user-bob": 2}),
        ]

        def _apply_votes(initial):
            state = initial
            for slot_id, node_id, ranks in votes:
                state = engine.record_vote(
                    state=state,
                    slot_id=slot_id,
                    chosen_node_id=node_id,
                    member_preference_ranks=ranks,
                )
            return state

        state_a = _apply_votes(empty_state)
        state_b = _apply_votes(empty_state)

        for mid in ["user-alice", "user-bob"]:
            assert state_a.members[mid].cumulative_debt == pytest.approx(
                state_b.members[mid].cumulative_debt
            )

    def test_state_serialization_round_trip(self, engine, empty_state):
        """FairnessState serializes to dict and back without data loss."""
        state = engine.record_vote(
            state=empty_state,
            slot_id="s1",
            chosen_node_id="n1",
            member_preference_ranks={"user-alice": 3, "user-bob": 1},
        )
        serialized = state.to_dict()
        restored = FairnessState.from_dict(serialized)

        assert restored.total_votes == state.total_votes
        for mid in ["user-alice", "user-bob"]:
            assert restored.members[mid].cumulative_debt == pytest.approx(
                state.members[mid].cumulative_debt
            )
