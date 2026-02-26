"""
Tests for scripts/bend_canary_report.py.

Covers:
- Report generation with mock data
- Tourist trap flag detection (tourist_score > 0.5)
- Low confidence flag detection (1 source, confidence < 0.4)
- Chain leakage detection
- Overrated flag extraction from extractionMetadata
- Missing category detection (outdoor cities missing outdoors/active)
- Vibe tag histogram construction
- JSON serialization produces valid output
- Terminal rendering includes all section headers
- Summary issues are populated correctly
"""

import json
from datetime import datetime, timezone

import pytest

# Import the module under test using its absolute path relative to the repo root.
# The script lives in scripts/ rather than a package, so we add it to sys.path
# in the conftest or import directly via importlib.
import importlib.util
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import the script as a module (it's not in a package)
# ---------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "bend_canary_report.py"


def _load_report_module():
    """Dynamically load bend_canary_report.py as a module."""
    spec = importlib.util.spec_from_file_location("bend_canary_report", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def rmod():
    """Module-scoped fixture for the report module."""
    return _load_report_module()


# ---------------------------------------------------------------------------
# Fixtures: synthetic ActivityNode + QualitySignal data
# ---------------------------------------------------------------------------

def _make_node(
    *,
    node_id: str = "node-001",
    name: str = "Test Venue",
    category: str = "dining",
    status: str = "approved",
    tourist_score: float = 0.2,
    convergence_score: float = 0.75,
    source_count: int = 3,
    vibe_tags: list = None,
) -> dict:
    return {
        "id": node_id,
        "name": name,
        "category": category,
        "status": status,
        "tourist_score": tourist_score,
        "convergenceScore": convergence_score,
        "sourceCount": source_count,
        "vibe_tags": vibe_tags or [],
    }


def _make_signal(
    *,
    node_id: str = "node-001",
    source_name: str = "reddit",
    raw_excerpt: str = "Great local spot",
    source_authority: float = 0.8,
    data_confidence: float = 0.75,
    overrated_flag: bool = False,
) -> dict:
    meta: dict = {"data_confidence": data_confidence}
    if overrated_flag:
        meta["overrated_flag"] = True
    return {
        "activityNodeId": node_id,
        "sourceName": source_name,
        "rawExcerpt": raw_excerpt,
        "sourceAuthority": source_authority,
        "extractionMetadata": json.dumps(meta),
    }


# ---------------------------------------------------------------------------
# Tests: build_node_report
# ---------------------------------------------------------------------------


class TestBuildNodeReport:
    def test_clean_node_has_no_flags(self, rmod):
        node = _make_node(tourist_score=0.2, convergence_score=0.8, source_count=3)
        signals = [
            _make_signal(data_confidence=0.8),
            _make_signal(source_name="foursquare", data_confidence=0.7),
        ]
        nr = rmod.build_node_report(node, signals)
        assert nr.flags == []

    def test_tourist_trap_flag_above_threshold(self, rmod):
        node = _make_node(tourist_score=0.65)
        nr = rmod.build_node_report(node, [_make_signal()])
        assert any("TOURIST TRAP" in f for f in nr.flags)

    def test_tourist_trap_flag_exactly_at_threshold(self, rmod):
        """tourist_score == threshold should NOT be flagged (strictly >)."""
        node = _make_node(tourist_score=0.5)
        nr = rmod.build_node_report(node, [_make_signal()])
        assert not any("TOURIST TRAP" in f for f in nr.flags)

    def test_tourist_trap_flag_below_threshold(self, rmod):
        node = _make_node(tourist_score=0.49)
        nr = rmod.build_node_report(node, [_make_signal()])
        assert not any("TOURIST TRAP" in f for f in nr.flags)

    def test_low_confidence_flag_one_source_low_confidence(self, rmod):
        node = _make_node(source_count=1)
        signals = [_make_signal(data_confidence=0.3)]
        nr = rmod.build_node_report(node, signals)
        assert any("LOW CONFIDENCE" in f for f in nr.flags)

    def test_low_confidence_flag_one_source_no_confidence_data(self, rmod):
        node = _make_node(source_count=1)
        signals = [{"activityNodeId": "x", "sourceName": "blog", "rawExcerpt": "good", "sourceAuthority": 0.5, "extractionMetadata": None}]
        nr = rmod.build_node_report(node, signals)
        assert any("LOW CONFIDENCE" in f for f in nr.flags)

    def test_no_low_confidence_flag_multiple_sources(self, rmod):
        """Multiple sources with low individual confidence should not trigger."""
        node = _make_node(source_count=3)
        signals = [
            _make_signal(source_name="reddit", data_confidence=0.3),
            _make_signal(source_name="foursquare", data_confidence=0.3),
            _make_signal(source_name="blog", data_confidence=0.3),
        ]
        nr = rmod.build_node_report(node, signals)
        assert not any("LOW CONFIDENCE" in f for f in nr.flags)

    def test_overrated_flag_from_metadata(self, rmod):
        node = _make_node()
        signals = [_make_signal(overrated_flag=True)]
        nr = rmod.build_node_report(node, signals)
        assert any("OVERRATED" in f for f in nr.flags)
        assert nr.overrated_flag_mentions == 1

    def test_overrated_flag_count_multiple(self, rmod):
        node = _make_node()
        signals = [
            _make_signal(overrated_flag=True),
            _make_signal(overrated_flag=True),
            _make_signal(overrated_flag=False),
        ]
        nr = rmod.build_node_report(node, signals)
        assert nr.overrated_flag_mentions == 2

    def test_chain_leakage_exact_match(self, rmod):
        node = _make_node(name="Starbucks")
        nr = rmod.build_node_report(node, [_make_signal()])
        assert any("CHAIN LEAKAGE" in f for f in nr.flags)

    def test_chain_leakage_starts_with(self, rmod):
        node = _make_node(name="McDonald's on Main Street")
        nr = rmod.build_node_report(node, [_make_signal()])
        assert any("CHAIN LEAKAGE" in f for f in nr.flags)

    def test_chain_leakage_case_insensitive(self, rmod):
        node = _make_node(name="SUBWAY")
        nr = rmod.build_node_report(node, [_make_signal()])
        assert any("CHAIN LEAKAGE" in f for f in nr.flags)

    def test_local_venue_not_flagged_as_chain(self, rmod):
        node = _make_node(name="Deschutes Brewery")
        nr = rmod.build_node_report(node, [_make_signal()])
        assert not any("CHAIN LEAKAGE" in f for f in nr.flags)


# ---------------------------------------------------------------------------
# Tests: source_breakdown + excerpts
# ---------------------------------------------------------------------------


class TestSignalAggregation:
    def test_source_breakdown_counts_per_source(self, rmod):
        node = _make_node()
        signals = [
            _make_signal(source_name="reddit"),
            _make_signal(source_name="reddit"),
            _make_signal(source_name="foursquare"),
        ]
        nr = rmod.build_node_report(node, signals)
        assert nr.source_breakdown["reddit"] == 2
        assert nr.source_breakdown["foursquare"] == 1

    def test_excerpts_capped_at_max(self, rmod):
        node = _make_node()
        signals = [_make_signal(raw_excerpt=f"excerpt {i}") for i in range(10)]
        nr = rmod.build_node_report(node, signals)
        assert len(nr.excerpts) <= rmod.MAX_EXCERPTS_PER_NODE

    def test_empty_excerpts_skipped(self, rmod):
        node = _make_node()
        signals = [
            _make_signal(raw_excerpt=""),
            _make_signal(raw_excerpt="  "),
            _make_signal(raw_excerpt="Real excerpt here"),
        ]
        nr = rmod.build_node_report(node, signals)
        assert len(nr.excerpts) == 1
        assert nr.excerpts[0] == "Real excerpt here"

    def test_avg_data_confidence_computed(self, rmod):
        node = _make_node()
        signals = [
            _make_signal(data_confidence=0.8),
            _make_signal(data_confidence=0.6),
        ]
        nr = rmod.build_node_report(node, signals)
        assert nr.avg_data_confidence == pytest.approx(0.7, abs=0.01)

    def test_avg_confidence_none_when_no_metadata(self, rmod):
        node = _make_node()
        signals = [
            {"activityNodeId": "x", "sourceName": "blog", "rawExcerpt": "good",
             "sourceAuthority": 0.5, "extractionMetadata": None},
        ]
        nr = rmod.build_node_report(node, signals)
        assert nr.avg_data_confidence is None


# ---------------------------------------------------------------------------
# Tests: assemble_report
# ---------------------------------------------------------------------------


class TestAssembleReport:
    def _base_node_rows(self):
        return [
            _make_node(node_id="n1", name="Deschutes Brewery", category="drinks",
                       tourist_score=0.2, convergence_score=0.9, source_count=4,
                       vibe_tags=["craft-beer", "locals-regular", "low-key"]),
            _make_node(node_id="n2", name="Pine Tavern", category="dining",
                       tourist_score=0.65, convergence_score=0.45, source_count=2,
                       vibe_tags=["instagram-worthy", "traditional", "overrated"]),
            _make_node(node_id="n3", name="Smith Rock State Park", category="outdoors",
                       tourist_score=0.1, convergence_score=0.95, source_count=5,
                       vibe_tags=["nature", "physical", "instagram-worthy"]),
        ]

    def _base_signals(self):
        return {
            "n1": [
                _make_signal(node_id="n1", source_name="reddit",
                             raw_excerpt="Best brewery in town, locals go here after work",
                             data_confidence=0.85),
                _make_signal(node_id="n1", source_name="foursquare",
                             data_confidence=0.8),
            ],
            "n2": [
                _make_signal(node_id="n2", source_name="blog",
                             raw_excerpt="Kind of a tourist spot honestly",
                             data_confidence=0.5, overrated_flag=True),
                _make_signal(node_id="n2", source_name="blog",
                             data_confidence=0.5),
            ],
            "n3": [
                _make_signal(node_id="n3", source_name="reddit",
                             data_confidence=0.9),
            ],
        }

    def test_total_nodes_count(self, rmod):
        report = rmod.assemble_report("Bend", self._base_node_rows(), self._base_signals())
        assert report.total_nodes == 3

    def test_flagged_tourist_traps_detected(self, rmod):
        report = rmod.assemble_report("Bend", self._base_node_rows(), self._base_signals())
        trap_names = [n.name for n in report.flagged_tourist_traps]
        assert "Pine Tavern" in trap_names
        assert "Deschutes Brewery" not in trap_names

    def test_category_distribution(self, rmod):
        report = rmod.assemble_report("Bend", self._base_node_rows(), self._base_signals())
        assert report.category_distribution["drinks"] == 1
        assert report.category_distribution["dining"] == 1
        assert report.category_distribution["outdoors"] == 1

    def test_vibe_tag_histogram(self, rmod):
        report = rmod.assemble_report("Bend", self._base_node_rows(), self._base_signals())
        # "instagram-worthy" appears in both Pine Tavern and Smith Rock
        assert report.vibe_tag_histogram.get("instagram-worthy", 0) == 2
        assert report.vibe_tag_histogram.get("craft-beer", 0) == 1

    def test_no_missing_categories_for_bend_with_outdoors(self, rmod):
        report = rmod.assemble_report("Bend", self._base_node_rows(), self._base_signals())
        assert "outdoors" not in report.missing_categories

    def test_missing_outdoor_category_flagged_for_bend(self, rmod):
        """If Bend has no outdoors/active nodes, it should be flagged."""
        nodes = [
            _make_node(node_id="n1", category="dining"),
            _make_node(node_id="n2", category="drinks"),
            _make_node(node_id="n3", category="culture"),
        ]
        report = rmod.assemble_report("Bend", nodes, {})
        assert len(report.missing_categories) > 0
        assert any(cat in ("outdoors", "active") for cat in report.missing_categories)

    def test_missing_outdoor_not_flagged_for_non_outdoor_city(self, rmod):
        """Non-outdoor cities shouldn't be penalized for missing outdoors."""
        nodes = [
            _make_node(node_id="n1", category="dining"),
            _make_node(node_id="n2", category="drinks"),
            _make_node(node_id="n3", category="culture"),
        ]
        report = rmod.assemble_report("New Orleans", nodes, {})
        # Should not flag missing outdoor category for New Orleans
        outdoor_flags = [c for c in report.missing_categories if c in ("outdoors", "active")]
        assert len(outdoor_flags) == 0

    def test_zero_nodes_triggers_critical_issue(self, rmod):
        report = rmod.assemble_report("Bend", [], {})
        assert any("Zero canonical nodes" in issue for issue in report.summary_issues)

    def test_chain_leakage_detected(self, rmod):
        nodes = [
            _make_node(node_id="n1", name="Starbucks"),
            _make_node(node_id="n2", name="Deschutes Brewery"),
        ]
        report = rmod.assemble_report("Bend", nodes, {})
        assert len(report.chain_leakage) == 1
        assert report.chain_leakage[0].name == "Starbucks"

    def test_no_issues_when_clean(self, rmod):
        nodes = [
            _make_node(node_id="n1", category="dining", tourist_score=0.1, source_count=3),
            _make_node(node_id="n2", category="outdoors", tourist_score=0.2, source_count=2),
            _make_node(node_id="n3", category="drinks", tourist_score=0.15, source_count=4),
            _make_node(node_id="n4", category="active", tourist_score=0.1, source_count=2),
        ]
        signals = {
            "n1": [_make_signal(data_confidence=0.8)],
            "n2": [_make_signal(data_confidence=0.9)],
            "n3": [_make_signal(data_confidence=0.7)],
            "n4": [_make_signal(data_confidence=0.8)],
        }
        report = rmod.assemble_report("Bend", nodes, signals)
        assert report.summary_issues == ["No critical issues detected"]

    def test_unique_sources_counted(self, rmod):
        signals = {
            "n1": [
                _make_signal(node_id="n1", source_name="reddit"),
                _make_signal(node_id="n1", source_name="foursquare"),
            ],
            "n2": [
                _make_signal(node_id="n2", source_name="blog"),
            ],
            "n3": [],
        }
        report = rmod.assemble_report("Bend", self._base_node_rows(), signals)
        assert report.unique_sources >= 2


# ---------------------------------------------------------------------------
# Tests: terminal rendering
# ---------------------------------------------------------------------------


class TestTerminalRendering:
    def _simple_report(self, rmod):
        nodes = [
            _make_node(node_id="n1", name="Deschutes Brewery", category="drinks",
                       tourist_score=0.2, vibe_tags=["craft-beer"]),
        ]
        return rmod.assemble_report("Bend", nodes, {
            "n1": [_make_signal(raw_excerpt="Best brewery in Bend")]
        })

    def test_header_present(self, rmod):
        report = self._simple_report(rmod)
        output = rmod.render_terminal_report(report)
        assert "BEND" in output
        assert "Canary Report" in output

    def test_node_count_in_header(self, rmod):
        report = self._simple_report(rmod)
        output = rmod.render_terminal_report(report)
        assert "Nodes: 1" in output

    def test_category_distribution_section(self, rmod):
        report = self._simple_report(rmod)
        output = rmod.render_terminal_report(report)
        assert "CATEGORY DISTRIBUTION" in output
        assert "drinks" in output

    def test_vibe_tag_histogram_section(self, rmod):
        report = self._simple_report(rmod)
        output = rmod.render_terminal_report(report)
        assert "VIBE TAG DISTRIBUTION" in output

    def test_summary_issues_section(self, rmod):
        report = self._simple_report(rmod)
        output = rmod.render_terminal_report(report)
        assert "SUMMARY" in output

    def test_all_nodes_section(self, rmod):
        report = self._simple_report(rmod)
        output = rmod.render_terminal_report(report)
        assert "ALL NODES" in output
        assert "Deschutes Brewery" in output

    def test_tourist_trap_section_absent_when_no_traps(self, rmod):
        report = self._simple_report(rmod)
        output = rmod.render_terminal_report(report)
        assert "TOURIST TRAP" not in output or "[FLAG: POSSIBLE TOURIST TRAP]" not in output

    def test_tourist_trap_section_present_when_traps(self, rmod):
        nodes = [
            _make_node(node_id="n1", name="Tourist Trap Cafe", category="dining",
                       tourist_score=0.8),
        ]
        report = rmod.assemble_report("Bend", nodes, {})
        output = rmod.render_terminal_report(report)
        assert "TOURIST TRAP" in output

    def test_excerpt_included_in_output(self, rmod):
        report = self._simple_report(rmod)
        output = rmod.render_terminal_report(report)
        assert "Best brewery in Bend" in output


# ---------------------------------------------------------------------------
# Tests: JSON serialization
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    def test_json_output_is_valid(self, rmod):
        nodes = [_make_node(node_id="n1")]
        report = rmod.assemble_report("Bend", nodes, {})
        d = rmod._report_to_dict(report)
        serialized = json.dumps(d)
        parsed = json.loads(serialized)
        assert parsed["city"] == "Bend"
        assert "total_nodes" in parsed
        assert "all_nodes" in parsed

    def test_json_all_nodes_have_required_keys(self, rmod):
        nodes = [_make_node(node_id="n1")]
        report = rmod.assemble_report("Bend", nodes, {})
        d = rmod._report_to_dict(report)
        for node_d in d["all_nodes"]:
            for key in ("id", "name", "category", "tourist_score", "convergence_score",
                        "vibe_tags", "source_count", "source_breakdown", "excerpts", "flags"):
                assert key in node_d, f"Missing key: {key}"

    def test_json_contains_category_distribution(self, rmod):
        nodes = [
            _make_node(node_id="n1", category="dining"),
            _make_node(node_id="n2", category="drinks"),
        ]
        report = rmod.assemble_report("Bend", nodes, {})
        d = rmod._report_to_dict(report)
        assert d["category_distribution"]["dining"] == 1
        assert d["category_distribution"]["drinks"] == 1

    def test_json_flagged_lists_are_subsets_of_all_nodes(self, rmod):
        nodes = [
            _make_node(node_id="n1", tourist_score=0.8, name="Tourist Spot"),
            _make_node(node_id="n2", tourist_score=0.1, name="Local Gem"),
        ]
        report = rmod.assemble_report("Bend", nodes, {})
        d = rmod._report_to_dict(report)
        flagged_ids = {n["id"] for n in d["flagged_tourist_traps"]}
        all_ids = {n["id"] for n in d["all_nodes"]}
        assert flagged_ids.issubset(all_ids)

    def test_json_vibe_histogram_present(self, rmod):
        nodes = [
            _make_node(node_id="n1", vibe_tags=["nature", "instagram-worthy"]),
            _make_node(node_id="n2", vibe_tags=["instagram-worthy", "calm"]),
        ]
        report = rmod.assemble_report("Bend", nodes, {})
        d = rmod._report_to_dict(report)
        assert d["vibe_tag_histogram"]["instagram-worthy"] == 2
        assert d["vibe_tag_histogram"]["nature"] == 1


# ---------------------------------------------------------------------------
# Tests: chain detection helper
# ---------------------------------------------------------------------------


class TestChainDetection:
    def test_known_chains_detected(self, rmod):
        chains = [
            "Starbucks", "McDonald's", "subway", "Chipotle",
            "Pizza Hut", "DUNKIN", "Taco Bell",
        ]
        for chain in chains:
            assert rmod._detect_chain_leakage(chain), f"{chain} should be detected as chain"

    def test_local_venues_not_flagged(self, rmod):
        local = [
            "Deschutes Brewery",
            "Pine Tavern",
            "Smith Rock Brewing",
            "Boneyard Beer",
            "The Lokal",
        ]
        for venue in local:
            assert not rmod._detect_chain_leakage(venue), f"{venue} should not be flagged"

    def test_partial_name_not_flagged(self, rmod):
        """A venue that contains 'subway' in the middle should not be flagged."""
        assert not rmod._detect_chain_leakage("The Old Subway Tunnel Bar")


# ---------------------------------------------------------------------------
# Tests: vibe tag histogram
# ---------------------------------------------------------------------------


class TestVibeTagHistogram:
    def test_histogram_counts_across_nodes(self, rmod):
        nodes = [
            _make_node(node_id="n1", vibe_tags=["nature", "instagram-worthy", "physical"]),
            _make_node(node_id="n2", vibe_tags=["instagram-worthy", "calm"]),
            _make_node(node_id="n3", vibe_tags=["physical", "rugged"]),
        ]
        report = rmod.assemble_report("Bend", nodes, {})
        hist = report.vibe_tag_histogram
        assert hist["instagram-worthy"] == 2
        assert hist["physical"] == 2
        assert hist["nature"] == 1
        assert hist["calm"] == 1
        assert hist["rugged"] == 1

    def test_histogram_sorted_descending(self, rmod):
        nodes = [
            _make_node(node_id="n1", vibe_tags=["a", "b", "c"]),
            _make_node(node_id="n2", vibe_tags=["a", "b"]),
            _make_node(node_id="n3", vibe_tags=["a"]),
        ]
        report = rmod.assemble_report("Bend", nodes, {})
        hist = report.vibe_tag_histogram
        counts = list(hist.values())
        assert counts == sorted(counts, reverse=True)

    def test_empty_vibe_tags_handled(self, rmod):
        nodes = [_make_node(node_id="n1", vibe_tags=[])]
        report = rmod.assemble_report("Bend", nodes, {})
        assert report.vibe_tag_histogram == {}
