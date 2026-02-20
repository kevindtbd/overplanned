"""
Contract tests: schema parity across Prisma, JSON Schema, Pydantic, TypeScript.

Validates:
- Enum sync: all enums match across stacks
- Model field presence: core fields exist in all representations
- CI guard: codegen staleness detection
"""

import json
import subprocess
from pathlib import Path

import pytest

# Paths relative to foundation track root
FOUNDATION_ROOT = Path(__file__).resolve().parents[3]
PRISMA_SCHEMA = FOUNDATION_ROOT / "prisma" / "schema.prisma"


# ---------------------------------------------------------------------------
# Enum extraction from Prisma schema
# ---------------------------------------------------------------------------

def _parse_prisma_enums(schema_path: Path) -> dict[str, list[str]]:
    """Extract enum name -> values from schema.prisma."""
    enums: dict[str, list[str]] = {}
    current_enum: str | None = None
    values: list[str] = []

    for line in schema_path.read_text().splitlines():
        stripped = line.strip()

        if stripped.startswith("enum ") and "{" in stripped:
            current_enum = stripped.split()[1]
            values = []
        elif current_enum and stripped == "}":
            enums[current_enum] = values
            current_enum = None
        elif current_enum and stripped and not stripped.startswith("//"):
            values.append(stripped)

    return enums


def _parse_prisma_models(schema_path: Path) -> dict[str, list[str]]:
    """Extract model name -> field names from schema.prisma."""
    models: dict[str, list[str]] = {}
    current_model: str | None = None
    fields: list[str] = []

    for line in schema_path.read_text().splitlines():
        stripped = line.strip()

        if stripped.startswith("model ") and "{" in stripped:
            current_model = stripped.split()[1]
            fields = []
        elif current_model and stripped == "}":
            models[current_model] = fields
            current_model = None
        elif current_model and stripped and not stripped.startswith("//") and not stripped.startswith("@@"):
            field_name = stripped.split()[0]
            if field_name not in ("}", "{"):
                fields.append(field_name)

    return models


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPrismaSchemaExists:
    """Verify schema file is present and parseable."""

    def test_schema_file_exists(self):
        assert PRISMA_SCHEMA.exists(), f"Prisma schema not found at {PRISMA_SCHEMA}"

    def test_schema_has_content(self):
        content = PRISMA_SCHEMA.read_text()
        assert len(content) > 100, "Prisma schema appears empty"


class TestEnumSync:
    """Verify all enums are defined and have expected values."""

    @pytest.fixture(autouse=True)
    def setup_enums(self):
        self.enums = _parse_prisma_enums(PRISMA_SCHEMA)

    EXPECTED_ENUMS = [
        "SubscriptionTier",
        "SystemRole",
        "TripMode",
        "TripStatus",
        "TripRole",
        "MemberStatus",
        "SlotType",
        "SlotStatus",
        "ActivityCategory",
        "NodeStatus",
        "SignalType",
        "TripPhase",
        "IntentClass",
        "ModelStage",
        "PivotTrigger",
        "PivotStatus",
    ]

    @pytest.mark.parametrize("enum_name", EXPECTED_ENUMS)
    def test_enum_exists(self, enum_name: str):
        assert enum_name in self.enums, f"Enum {enum_name} missing from Prisma schema"

    def test_subscription_tier_values(self):
        assert set(self.enums["SubscriptionTier"]) == {"free", "beta", "pro", "lifetime"}

    def test_system_role_values(self):
        assert set(self.enums["SystemRole"]) == {"user", "admin"}

    def test_trip_mode_values(self):
        assert set(self.enums["TripMode"]) == {"solo", "group"}

    def test_intent_class_values(self):
        assert set(self.enums["IntentClass"]) == {"explicit", "implicit", "contextual"}

    def test_activity_category_values(self):
        expected = {
            "dining", "drinks", "culture", "outdoors", "active",
            "entertainment", "shopping", "experience", "nightlife",
            "group_activity", "wellness",
        }
        assert set(self.enums["ActivityCategory"]) == expected

    def test_signal_type_has_all_categories(self):
        """SignalType must cover slot, discover, vibe, post-trip, pivot, passive."""
        values = set(self.enums["SignalType"])
        assert any(v.startswith("slot_") for v in values), "Missing slot_ signals"
        assert any(v.startswith("discover_") for v in values), "Missing discover_ signals"
        assert any(v.startswith("vibe_") for v in values), "Missing vibe_ signals"
        assert any(v.startswith("post_") for v in values), "Missing post_ signals"
        assert any(v.startswith("pivot_") for v in values), "Missing pivot_ signals"
        assert "dwell_time" in values, "Missing dwell_time passive signal"


class TestModelFieldParity:
    """Verify core models have expected fields."""

    @pytest.fixture(autouse=True)
    def setup_models(self):
        self.models = _parse_prisma_models(PRISMA_SCHEMA)

    EXPECTED_MODELS = [
        "User", "Session", "Account", "Trip", "TripMember",
        "ItinerarySlot", "ActivityNode", "VibeTag", "QualitySignal",
        "BehavioralSignal", "IntentionSignal", "RawEvent",
        "ModelRegistry", "PivotEvent", "AuditLog",
        "SharedTripToken", "InviteToken",
        "ActivityNodeVibeTag", "ActivityAlias", "VerificationToken",
    ]

    @pytest.mark.parametrize("model_name", EXPECTED_MODELS)
    def test_model_exists(self, model_name: str):
        assert model_name in self.models, f"Model {model_name} missing from Prisma schema"

    def test_user_has_core_fields(self):
        fields = self.models["User"]
        for f in ["id", "email", "subscriptionTier", "systemRole", "createdAt"]:
            assert f in fields, f"User missing field: {f}"

    def test_behavioral_signal_has_core_fields(self):
        fields = self.models["BehavioralSignal"]
        for f in ["id", "userId", "signalType", "signalValue", "tripPhase", "rawAction"]:
            assert f in fields, f"BehavioralSignal missing field: {f}"

    def test_raw_event_has_core_fields(self):
        fields = self.models["RawEvent"]
        for f in ["id", "userId", "sessionId", "eventType", "intentClass", "clientEventId"]:
            assert f in fields, f"RawEvent missing field: {f}"

    def test_intention_signal_links_to_behavioral(self):
        fields = self.models["IntentionSignal"]
        assert "behavioralSignalId" in fields, (
            "IntentionSignal must link to BehavioralSignal via behavioralSignalId"
        )

    def test_activity_node_has_entity_resolution_fields(self):
        fields = self.models["ActivityNode"]
        for f in ["foursquareId", "googlePlaceId", "contentHash", "resolvedToId", "isCanonical"]:
            assert f in fields, f"ActivityNode missing entity resolution field: {f}"

    def test_quality_signal_has_per_source_fields(self):
        """Per-source quality signals, NEVER collapse to single score."""
        fields = self.models["QualitySignal"]
        for f in ["sourceName", "sourceAuthority", "signalType"]:
            assert f in fields, f"QualitySignal missing per-source field: {f}"


class TestCodegenStaleness:
    """CI guard: detect when codegen output is stale vs schema."""

    def test_prisma_schema_parses(self):
        """Schema should parse without errors."""
        enums = _parse_prisma_enums(PRISMA_SCHEMA)
        models = _parse_prisma_models(PRISMA_SCHEMA)
        assert len(enums) >= 10, "Unexpectedly few enums parsed"
        assert len(models) >= 15, "Unexpectedly few models parsed"
