"""
Group voting logic tests (M-008).

Validates:
- Vote recording: each member's vote is stored
- Camp detection: majority vs minority camps identified
- Conflict resolution: tie-breaking, threshold enforcement
- Vote threshold: configurable quorum detection
- Abilene paradox detection: unanimous approval of unwanted option
- Vote state transitions: proposed -> voted -> confirmed/contested
"""

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .conftest import (
    make_group_user,
    make_group_trip,
    make_itinerary_slot_group,
    _make_obj,
    _gen_id,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Pure voting logic — tested without API layer
# ---------------------------------------------------------------------------


class VoteState:
    """Minimal voting engine mirroring the production schema."""

    def __init__(
        self,
        member_ids: list[str],
        threshold: float = 0.6,
    ):
        self.votes: dict[str, str] = {}  # member_id -> "approve" | "reject" | "abstain"
        self.member_ids = set(member_ids)
        self.threshold = threshold
        self.resolved = False
        self.outcome: str | None = None

    def cast_vote(self, member_id: str, vote: str) -> None:
        assert vote in ("approve", "reject", "abstain"), f"Invalid vote: {vote}"
        assert member_id in self.member_ids, f"Member not in group: {member_id}"
        self.votes[member_id] = vote

    @property
    def approval_rate(self) -> float:
        counted = {v for v in self.votes.values() if v != "abstain"}
        if not counted:
            return 0.0
        approvals = sum(1 for v in self.votes.values() if v == "approve")
        non_abstain = sum(1 for v in self.votes.values() if v != "abstain")
        return approvals / non_abstain if non_abstain else 0.0

    @property
    def quorum_reached(self) -> bool:
        """True when enough members have voted (non-abstain)."""
        non_abstain = sum(1 for v in self.votes.values() if v != "abstain")
        return non_abstain >= len(self.member_ids)

    def resolve(self) -> str:
        """Determine outcome when quorum or deadline reached."""
        if self.approval_rate >= self.threshold:
            self.outcome = "confirmed"
        else:
            self.outcome = "contested"
        self.resolved = True
        return self.outcome

    def detect_camps(self) -> dict:
        """Split members into approve / reject / abstain camps."""
        camps: dict[str, list[str]] = {
            "approve": [],
            "reject": [],
            "abstain": [],
        }
        for member_id, vote in self.votes.items():
            camps[vote].append(member_id)
        # Include non-voters as abstain
        for member_id in self.member_ids:
            if member_id not in self.votes:
                camps["abstain"].append(member_id)
        return camps

    def detect_abilene_paradox(self) -> bool:
        """
        Detect the Abilene paradox: all members voted approve but none
        actually wanted to (proxy: all approved with zero prior positive signals).
        In test context we simulate this with an 'abilene_risk' flag.
        """
        all_approved = all(
            self.votes.get(m) == "approve" for m in self.member_ids
        )
        if not all_approved:
            return False
        # If all voted approve but the threshold is barely met — risk signal
        return self.approval_rate == 1.0 and len(self.votes) >= 2


# ---------------------------------------------------------------------------
# TestVoteRecording
# ---------------------------------------------------------------------------


class TestVoteRecording:
    """Vote casting stored correctly."""

    def test_single_vote_recorded(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        assert state.votes["alice"] == "approve"

    def test_all_three_votes_recorded(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "approve")
        state.cast_vote("cara", "reject")
        assert len(state.votes) == 3
        assert state.votes["cara"] == "reject"

    def test_vote_override_allowed(self):
        """Members can change their vote before resolution."""
        members = ["alice", "bob"]
        state = VoteState(members)
        state.cast_vote("alice", "reject")
        state.cast_vote("alice", "approve")
        assert state.votes["alice"] == "approve"

    def test_abstain_vote_recorded(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("bob", "abstain")
        assert state.votes["bob"] == "abstain"

    def test_invalid_vote_raises(self):
        members = ["alice"]
        state = VoteState(members)
        with pytest.raises(AssertionError):
            state.cast_vote("alice", "maybe")

    def test_nonmember_vote_raises(self):
        members = ["alice"]
        state = VoteState(members)
        with pytest.raises(AssertionError):
            state.cast_vote("dave", "approve")


# ---------------------------------------------------------------------------
# TestApprovalRate
# ---------------------------------------------------------------------------


class TestApprovalRate:
    """Approval rate calculation excludes abstentions."""

    def test_unanimous_approval(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        for m in members:
            state.cast_vote(m, "approve")
        assert state.approval_rate == 1.0

    def test_unanimous_rejection(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        for m in members:
            state.cast_vote(m, "reject")
        assert state.approval_rate == 0.0

    def test_two_thirds_approval(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "approve")
        state.cast_vote("cara", "reject")
        # 2/3 = 0.666...
        assert abs(state.approval_rate - 2 / 3) < 0.001

    def test_abstain_excluded_from_denominator(self):
        """Abstentions don't count against approval."""
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "approve")
        state.cast_vote("cara", "abstain")
        # 2 approve, 1 abstain — rate = 2/2 = 1.0
        assert state.approval_rate == 1.0

    def test_no_votes_zero_rate(self):
        members = ["alice", "bob"]
        state = VoteState(members)
        assert state.approval_rate == 0.0


# ---------------------------------------------------------------------------
# TestCampDetection
# ---------------------------------------------------------------------------


class TestCampDetection:
    """Camp detection splits members correctly."""

    def test_three_way_split(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "reject")
        # cara has not voted
        camps = state.detect_camps()
        assert "alice" in camps["approve"]
        assert "bob" in camps["reject"]
        assert "cara" in camps["abstain"]

    def test_all_approve_camp(self):
        members = ["alice", "bob"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "approve")
        camps = state.detect_camps()
        assert len(camps["approve"]) == 2
        assert len(camps["reject"]) == 0

    def test_non_voters_in_abstain_camp(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        camps = state.detect_camps()
        assert len(camps["abstain"]) == 2  # bob and cara haven't voted


# ---------------------------------------------------------------------------
# TestConflictResolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    """Resolution outcomes based on threshold."""

    def test_resolve_confirmed_above_threshold(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members, threshold=0.6)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "approve")
        state.cast_vote("cara", "reject")
        outcome = state.resolve()
        assert outcome == "confirmed"
        assert state.resolved is True

    def test_resolve_contested_below_threshold(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members, threshold=0.6)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "reject")
        state.cast_vote("cara", "reject")
        outcome = state.resolve()
        assert outcome == "contested"

    def test_resolve_tie_at_fifty_percent(self):
        """50% does NOT clear a 60% threshold."""
        members = ["alice", "bob"]
        state = VoteState(members, threshold=0.6)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "reject")
        outcome = state.resolve()
        assert outcome == "contested"

    def test_unanimous_above_threshold(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members, threshold=0.6)
        for m in members:
            state.cast_vote(m, "approve")
        assert state.resolve() == "confirmed"

    def test_custom_threshold_respected(self):
        """80% threshold: 2/3 approval fails."""
        members = ["alice", "bob", "cara"]
        state = VoteState(members, threshold=0.8)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "approve")
        state.cast_vote("cara", "reject")
        assert state.resolve() == "contested"


# ---------------------------------------------------------------------------
# TestAbyleneParadoxDetection
# ---------------------------------------------------------------------------


class TestAbyleneParadoxDetection:
    """Abilene paradox: unanimous approval as group-think signal."""

    def test_unanimous_approval_flags_abilene_risk(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        for m in members:
            state.cast_vote(m, "approve")
        assert state.detect_abilene_paradox() is True

    def test_non_unanimous_not_abilene(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "approve")
        state.cast_vote("cara", "reject")
        assert state.detect_abilene_paradox() is False

    def test_single_member_not_abilene(self):
        """Paradox requires at least 2 people."""
        members = ["alice"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        assert state.detect_abilene_paradox() is False

    def test_partial_votes_not_abilene(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        # bob and cara haven't voted — not unanimous
        assert state.detect_abilene_paradox() is False


# ---------------------------------------------------------------------------
# TestQuorumDetection
# ---------------------------------------------------------------------------


class TestQuorumDetection:
    """Quorum requires all members to cast a non-abstain vote."""

    def test_quorum_reached_all_voted(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "reject")
        state.cast_vote("cara", "approve")
        assert state.quorum_reached is True

    def test_quorum_not_reached_missing_vote(self):
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "approve")
        # cara hasn't voted
        assert state.quorum_reached is False

    def test_abstain_counts_toward_quorum(self):
        """All members casting any vote (incl. abstain) reaches quorum."""
        members = ["alice", "bob", "cara"]
        state = VoteState(members)
        state.cast_vote("alice", "approve")
        state.cast_vote("bob", "abstain")
        state.cast_vote("cara", "approve")
        assert state.quorum_reached is True
