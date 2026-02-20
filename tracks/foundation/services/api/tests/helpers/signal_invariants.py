"""
Signal integrity invariant checker.

Validates:
- No orphan signals (BehavioralSignal.userId must reference a valid user)
- Valid foreign keys on all signal models
- Required fields present and non-null
- IntentionSignal always links to a BehavioralSignal
- RawEvent always has eventType and intentClass

Reusable across all tracks:
    from services.api.tests.helpers.signal_invariants import assert_signal_integrity
"""

from __future__ import annotations

from typing import Any, Protocol


class DBProtocol(Protocol):
    """Minimal async DB interface for invariant checks."""
    async def fetch(self, query: str, *args: Any) -> list[dict]:
        ...


class SignalIntegrityError(Exception):
    """Raised when signal data violates an invariant."""

    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__(f"{len(violations)} signal integrity violation(s):\n" +
                         "\n".join(f"  - {v}" for v in violations))


async def assert_signal_integrity(db: DBProtocol) -> None:
    """Run all signal invariant checks against the database.

    Raises SignalIntegrityError if any violations are found.
    """
    violations: list[str] = []

    # 1. Orphan BehavioralSignals — userId must exist in User table
    orphan_bs = await db.fetch(
        """
        SELECT bs.id, bs."userId"
        FROM "BehavioralSignal" bs
        LEFT JOIN "User" u ON bs."userId" = u.id
        WHERE u.id IS NULL
        """
    )
    for row in orphan_bs:
        violations.append(
            f"Orphan BehavioralSignal {row['id']}: userId={row['userId']} not in User table"
        )

    # 2. BehavioralSignal required fields
    null_required_bs = await db.fetch(
        """
        SELECT id FROM "BehavioralSignal"
        WHERE "signalType" IS NULL
           OR "signalValue" IS NULL
           OR "tripPhase" IS NULL
           OR "rawAction" IS NULL
        """
    )
    for row in null_required_bs:
        violations.append(
            f"BehavioralSignal {row['id']}: missing required field(s)"
        )

    # 3. IntentionSignal must link to existing BehavioralSignal
    orphan_is = await db.fetch(
        """
        SELECT ins.id, ins."behavioralSignalId"
        FROM "IntentionSignal" ins
        LEFT JOIN "BehavioralSignal" bs ON ins."behavioralSignalId" = bs.id
        WHERE bs.id IS NULL
        """
    )
    for row in orphan_is:
        violations.append(
            f"Orphan IntentionSignal {row['id']}: "
            f"behavioralSignalId={row['behavioralSignalId']} not in BehavioralSignal table"
        )

    # 4. IntentionSignal required fields
    null_required_is = await db.fetch(
        """
        SELECT id FROM "IntentionSignal"
        WHERE "intentionType" IS NULL
           OR confidence IS NULL
           OR source IS NULL
        """
    )
    for row in null_required_is:
        violations.append(
            f"IntentionSignal {row['id']}: missing required field(s)"
        )

    # 5. RawEvent required fields
    null_required_re = await db.fetch(
        """
        SELECT id FROM "RawEvent"
        WHERE "eventType" IS NULL
           OR "intentClass" IS NULL
           OR "userId" IS NULL
           OR "sessionId" IS NULL
        """
    )
    for row in null_required_re:
        violations.append(
            f"RawEvent {row['id']}: missing required field(s)"
        )

    # 6. RawEvent intentClass must be valid enum value
    invalid_intent = await db.fetch(
        """
        SELECT id, "intentClass" FROM "RawEvent"
        WHERE "intentClass" NOT IN ('explicit', 'implicit', 'contextual')
        """
    )
    for row in invalid_intent:
        violations.append(
            f"RawEvent {row['id']}: invalid intentClass={row['intentClass']}"
        )

    # 7. BehavioralSignal activityNodeId FK check (if present)
    orphan_bs_node = await db.fetch(
        """
        SELECT bs.id, bs."activityNodeId"
        FROM "BehavioralSignal" bs
        LEFT JOIN "ActivityNode" an ON bs."activityNodeId" = an.id
        WHERE bs."activityNodeId" IS NOT NULL AND an.id IS NULL
        """
    )
    for row in orphan_bs_node:
        violations.append(
            f"BehavioralSignal {row['id']}: "
            f"activityNodeId={row['activityNodeId']} not in ActivityNode table"
        )

    if violations:
        raise SignalIntegrityError(violations)
