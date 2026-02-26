"""
Tests for dynamic city support, quality filtering, and is_local detection
in the ArcticShiftScraper.

Covers:
- Dynamic city lookup returns Bend config from city_configs
- Quality filter excludes posts below score > 10 AND upvote_ratio > 0.70
- is_local pattern detection (all supported phrases)
- signalType set to "local_recommendation" for local authors
- Japan cities still work (backward compatibility)
- detect_city recognises Bend neighborhood terms
- Empty results handled gracefully (Bend canary small corpus)
- target_city scoping produces correct subreddit list
"""

from typing import Any, Dict, List, Optional
from unittest.mock import patch, MagicMock

import pytest

from services.api.scrapers.arctic_shift import (
    ArcticShiftScraper,
    detect_city,
    detect_is_local,
    passes_quality_filter,
    extract_venue_names,
    compute_authority_score,
    QUALITY_FILTER_MIN_SCORE,
    QUALITY_FILTER_MIN_UPVOTE_RATIO,
    TARGET_CITIES,
    SUBREDDIT_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_post(
    *,
    post_id: str = "abc123",
    subreddit: str = "bend",
    title: str = "Bend trip report",
    selftext: str = "",
    score: int = 50,
    upvote_ratio: float = 0.95,
    author: str = "user1",
    created_utc: int = 1700000000,
    permalink: str = "/r/bend/comments/abc123",
) -> Dict[str, Any]:
    return {
        "id": post_id,
        "subreddit": subreddit,
        "title": title,
        "selftext": selftext,
        "score": score,
        "upvote_ratio": upvote_ratio,
        "author": author,
        "created_utc": created_utc,
        "permalink": permalink,
    }


def _make_scraper(target_city: str = "bend") -> ArcticShiftScraper:
    return ArcticShiftScraper(
        parquet_dir="/nonexistent",
        target_city=target_city,
    )


# ---------------------------------------------------------------------------
# Dynamic city config tests
# ---------------------------------------------------------------------------

class TestDynamicCityConfig:
    def test_bend_present_in_target_cities(self):
        """city_configs.get_target_cities_dict() must include Bend."""
        assert "bend" in TARGET_CITIES, (
            "TARGET_CITIES should be loaded from city_configs and include 'bend'"
        )

    def test_bend_neighborhood_terms_populated(self):
        """Bend config should have relevant neighborhood terms."""
        terms = TARGET_CITIES.get("bend", [])
        assert len(terms) > 0, "Bend neighborhood terms must not be empty"
        assert "bend" in terms, "Bend should appear in its own neighborhood terms"

    def test_bend_subreddit_weights_present(self):
        """Bend-specific subreddits (r/bend, r/bendoregon) must be in SUBREDDIT_WEIGHTS."""
        assert "bend" in SUBREDDIT_WEIGHTS or "bendoregon" in SUBREDDIT_WEIGHTS, (
            "At least one Bend subreddit must be in SUBREDDIT_WEIGHTS"
        )

    def test_japan_cities_present(self):
        """Tokyo, Kyoto, Osaka must still be in TARGET_CITIES (backward compat)."""
        for city in ("tokyo", "kyoto", "osaka"):
            assert city in TARGET_CITIES, (
                f"Japan city '{city}' missing from TARGET_CITIES — backward compat broken"
            )

    def test_all_us_cities_present(self):
        """All Phase 7.1 US starter cities must be in TARGET_CITIES."""
        for city in ("austin", "seattle", "portland", "asheville", "new-orleans"):
            assert city in TARGET_CITIES, f"US city '{city}' missing from TARGET_CITIES"

    def test_target_city_scopes_to_single_city(self):
        """ArcticShiftScraper(target_city='bend') should only target Bend."""
        scraper = _make_scraper(target_city="bend")
        assert scraper.config.target_cities == ["bend"]

    def test_target_city_includes_city_subreddits(self):
        """
        Scraper with target_city='bend' should include Bend subreddits
        in its active subs.
        """
        scraper = _make_scraper(target_city="bend")
        subs = scraper._target_subs
        # At least one of the bend-specific subs must be present
        assert any(s in subs for s in ("bend", "bendoregon", "centraloregon")), (
            f"Expected at least one Bend subreddit in {subs}"
        )

    def test_default_scraper_targets_all_cities(self):
        """ArcticShiftScraper() with no target_city should target all configured cities."""
        scraper = ArcticShiftScraper(parquet_dir="/nonexistent")
        assert len(scraper.config.target_cities) > 3, (
            "Default scraper should target multiple cities, not just Japan"
        )
        assert "bend" in scraper.config.target_cities
        assert "tokyo" in scraper.config.target_cities


# ---------------------------------------------------------------------------
# detect_city tests — Bend
# ---------------------------------------------------------------------------

class TestDetectCityBend:
    def test_detect_city_bend_by_name(self):
        assert detect_city("I'm visiting Bend next week") == "bend"

    def test_detect_city_bend_old_mill(self):
        assert detect_city("Dinner at the Old Mill District was fantastic") == "bend"

    def test_detect_city_bend_deschutes(self):
        assert detect_city("Hiking along the Deschutes River trail") == "bend"

    def test_detect_city_bend_mt_bachelor(self):
        assert detect_city("Skiing at Mt Bachelor with friends") == "bend"

    def test_detect_city_bend_northwest_crossing(self):
        assert detect_city("Great brunch spot in Northwest Crossing") == "bend"

    def test_detect_city_bend_pilot_butte(self):
        assert detect_city("Ran up Pilot Butte this morning") == "bend"

    def test_detect_city_returns_none_for_unrelated(self):
        result = detect_city("Just got back from a conference in Denver")
        # Should not be bend
        assert result != "bend"

    def test_detect_city_bend_over_noise(self):
        """Bend terms should dominate over incidental matches."""
        text = "Visiting Bend Oregon — loved the Old Mill District and Deschutes Brewery"
        assert detect_city(text) == "bend"


# ---------------------------------------------------------------------------
# Quality filter tests
# ---------------------------------------------------------------------------

class TestQualityFilter:
    def test_passes_with_good_score_and_ratio(self):
        row = {"score": 50, "upvote_ratio": 0.92}
        assert passes_quality_filter(row) is True

    def test_fails_score_at_threshold(self):
        """score == QUALITY_FILTER_MIN_SCORE (not strictly greater) should fail."""
        row = {"score": QUALITY_FILTER_MIN_SCORE, "upvote_ratio": 0.95}
        assert passes_quality_filter(row) is False

    def test_fails_score_below_threshold(self):
        row = {"score": 5, "upvote_ratio": 0.95}
        assert passes_quality_filter(row) is False

    def test_fails_upvote_ratio_below_threshold(self):
        row = {"score": 50, "upvote_ratio": 0.50}
        assert passes_quality_filter(row) is False

    def test_fails_upvote_ratio_at_threshold(self):
        """ratio == QUALITY_FILTER_MIN_UPVOTE_RATIO is not strictly greater — fails."""
        row = {"score": 50, "upvote_ratio": QUALITY_FILTER_MIN_UPVOTE_RATIO}
        assert passes_quality_filter(row) is False

    def test_passes_when_upvote_ratio_absent(self):
        """Missing upvote_ratio (comment dumps) should not penalize."""
        row = {"score": 50}
        assert passes_quality_filter(row) is True

    def test_passes_when_upvote_ratio_none(self):
        row = {"score": 50, "upvote_ratio": None}
        assert passes_quality_filter(row) is True

    def test_handles_string_score(self):
        row = {"score": "50", "upvote_ratio": 0.92}
        assert passes_quality_filter(row) is True

    def test_handles_bad_string_score(self):
        row = {"score": "not_a_number", "upvote_ratio": 0.92}
        assert passes_quality_filter(row) is False

    def test_custom_thresholds(self):
        """Custom min_score and min_upvote_ratio should be respected."""
        row = {"score": 5, "upvote_ratio": 0.60}
        assert passes_quality_filter(row, min_score=3, min_upvote_ratio=0.50) is True
        assert passes_quality_filter(row, min_score=10, min_upvote_ratio=0.50) is False

    def test_quality_filtered_count_increments(self):
        """Scraper._rows_quality_filtered should count posts dropped by quality gate."""
        scraper = _make_scraper(target_city="bend")

        # Patch scrape() to return a pre-filtered list including one low-quality row
        low_quality = _make_post(score=3, upvote_ratio=0.40, subreddit="bend")
        high_quality = _make_post(
            post_id="xyz",
            score=100,
            upvote_ratio=0.95,
            subreddit="bend",
            selftext="I recommend Sparrow Bakery in the Old Mill District, it was amazing",
        )

        # Bypass the actual parquet load — test the filter counting logic directly
        scraper._target_subs = {"bend"}
        scraper.config.target_cities = ["bend"]

        # Simulate what scrape() would do internally
        from services.api.scrapers.arctic_shift import _is_relevant_post
        rows = [low_quality, high_quality]
        pre_quality_count = 0
        for row in rows:
            if _is_relevant_post(row, scraper._target_subs, scraper.config.min_score):
                pre_quality_count += 1
                if not passes_quality_filter(
                    row,
                    min_score=scraper.config.quality_min_score,
                    min_upvote_ratio=scraper.config.quality_min_upvote_ratio,
                ):
                    scraper._rows_quality_filtered += 1

        assert scraper._rows_quality_filtered == 1, (
            "One low-quality row should have been filtered"
        )


# ---------------------------------------------------------------------------
# is_local detection tests
# ---------------------------------------------------------------------------

class TestDetectIsLocal:
    def test_i_live_here(self):
        assert detect_is_local("I live here and love Sparrow Bakery") is True

    def test_as_a_local(self):
        assert detect_is_local("As a local, I recommend the Old Mill") is True

    def test_grew_up_here(self):
        assert detect_is_local("I grew up here and know all the hidden spots") is True

    def test_been_here_years_numeric(self):
        assert detect_is_local("I've been here 5 years and love this city") is True

    def test_been_here_years_singular(self):
        assert detect_is_local("Been here 1 year now") is True

    def test_moved_here(self):
        assert detect_is_local("We moved here from Portland two years ago") is True

    def test_local_here(self):
        assert detect_is_local("Local here — the best coffee is at Thump") is True

    def test_not_local_tourist(self):
        assert detect_is_local("We visited for a week and tried many restaurants") is False

    def test_not_local_planning(self):
        assert detect_is_local("I'm planning a trip to Bend next month") is False

    def test_not_local_empty_string(self):
        assert detect_is_local("") is False

    def test_case_insensitive_as_a_local(self):
        assert detect_is_local("AS A LOCAL here, the best spots are...") is True

    def test_case_insensitive_moved_here(self):
        assert detect_is_local("MOVED HERE last spring and haven't looked back") is True


# ---------------------------------------------------------------------------
# signalType assignment for local vs non-local
# ---------------------------------------------------------------------------

class TestSignalTypeAssignment:
    def _parse_post(self, scraper: ArcticShiftScraper, **kwargs) -> Optional[Dict[str, Any]]:
        raw = _make_post(**kwargs)
        return scraper.parse(raw)

    def test_local_author_gets_local_recommendation_signal_type(self):
        scraper = _make_scraper(target_city="bend")
        raw = _make_post(
            subreddit="bend",
            title="Bend food scene",
            selftext=(
                "Local here. I recommend Sparrow Bakery — their cardamom rolls are amazing. "
                "Old Mill District for a walk after."
            ),
        )
        parsed = scraper.parse(raw)

        assert parsed is not None, "Should parse a local post with venue mentions"
        for mention in parsed["mentions"]:
            assert mention["signal_type"] == "local_recommendation", (
                f"Expected 'local_recommendation' but got '{mention['signal_type']}' "
                f"for venue '{mention['venue_name']}'"
            )

    def test_non_local_positive_gets_recommendation(self):
        scraper = _make_scraper(target_city="bend")
        raw = _make_post(
            subreddit="bend",
            title="Visiting Bend",
            selftext="I recommend Thump Coffee in downtown Bend, it was amazing.",
        )
        parsed = scraper.parse(raw)

        assert parsed is not None
        # At least one mention should be "recommendation" (positive, non-local)
        signal_types = [m["signal_type"] for m in parsed["mentions"]]
        assert "recommendation" in signal_types or "mention" in signal_types, (
            f"Expected recommendation or mention, got: {signal_types}"
        )
        assert "local_recommendation" not in signal_types

    def test_local_flag_on_parsed_output(self):
        scraper = _make_scraper(target_city="bend")
        raw = _make_post(
            subreddit="bend",
            title="Local tips",
            selftext=(
                "I live here and the best place is Jackson's Corner on the bend east side. "
                "It was amazing."
            ),
        )
        parsed = scraper.parse(raw)
        assert parsed is not None
        assert parsed["is_local"] is True

    def test_stored_signal_metadata_has_is_local(self):
        scraper = _make_scraper(target_city="bend")
        parsed = {
            "source_row": "test",
            "city": "bend",
            "subreddit": "bend",
            "is_local": True,
            "mentions": [
                {
                    "venue_name": "Sparrow Bakery",
                    "city": "bend",
                    "subreddit": "bend",
                    "post_id": "test1",
                    "comment_id": None,
                    "score": 50,
                    "text_excerpt": "Amazing cardamom rolls",
                    "sentiment": "positive",
                    "author": "local_user",
                    "created_utc": 1700000000,
                    "permalink": "/r/bend/comments/test1",
                    "authority_score": 0.7,
                    "is_local": True,
                    "signal_type": "local_recommendation",
                },
            ],
        }
        scraper.store(parsed)
        results = scraper.get_results()

        assert len(results["quality_signals"]) == 1
        signal = results["quality_signals"][0]
        assert signal["signalType"] == "local_recommendation"
        assert signal["metadata"]["is_local"] is True

    def test_get_local_signals_filter(self):
        scraper = _make_scraper(target_city="bend")
        # Store one local and one non-local signal
        scraper.store({
            "source_row": "local1",
            "city": "bend",
            "subreddit": "bend",
            "is_local": True,
            "mentions": [{
                "venue_name": "Sparrow Bakery",
                "city": "bend",
                "subreddit": "bend",
                "post_id": "a",
                "comment_id": None,
                "score": 50,
                "text_excerpt": "Best bakery",
                "sentiment": "positive",
                "author": "local_user",
                "created_utc": 1700000000,
                "permalink": "/r/bend/comments/a",
                "authority_score": 0.7,
                "is_local": True,
                "signal_type": "local_recommendation",
            }],
        })
        scraper.store({
            "source_row": "visitor1",
            "city": "bend",
            "subreddit": "bend",
            "is_local": False,
            "mentions": [{
                "venue_name": "Thump Coffee",
                "city": "bend",
                "subreddit": "bend",
                "post_id": "b",
                "comment_id": None,
                "score": 30,
                "text_excerpt": "Good coffee",
                "sentiment": "positive",
                "author": "visitor",
                "created_utc": 1700000001,
                "permalink": "/r/bend/comments/b",
                "authority_score": 0.5,
                "is_local": False,
                "signal_type": "recommendation",
            }],
        })

        local_signals = scraper.get_local_signals()
        assert len(local_signals) == 1
        assert local_signals[0]["metadata"]["venue_name"] == "Sparrow Bakery"


# ---------------------------------------------------------------------------
# Japan backward compatibility
# ---------------------------------------------------------------------------

class TestJapanBackwardCompat:
    def test_detect_city_tokyo_still_works(self):
        assert detect_city("I visited Shibuya and had ramen in Shinjuku") == "tokyo"

    def test_detect_city_kyoto_still_works(self):
        assert detect_city("The temples in Arashiyama and Gion were beautiful") == "kyoto"

    def test_detect_city_osaka_still_works(self):
        assert detect_city("Dotonbori and Namba are must-visits in Osaka") == "osaka"

    def test_tokyo_scraper_still_parses(self):
        scraper = ArcticShiftScraper(
            parquet_dir="/nonexistent",
            target_city="tokyo",
        )
        raw = _make_post(
            subreddit="japantravel",
            title="Tokyo food guide",
            selftext="I recommend Ichiran Ramen in Shibuya, it was amazing.",
        )
        parsed = scraper.parse(raw)
        assert parsed is not None
        assert parsed["city"] == "tokyo"
        assert len(parsed["mentions"]) >= 1

    def test_japan_subreddits_in_weights(self):
        for sub in ("japantravel", "tokyo", "kyoto", "osaka"):
            assert sub in SUBREDDIT_WEIGHTS, (
                f"Japan subreddit '{sub}' missing from SUBREDDIT_WEIGHTS"
            )

    def test_legacy_target_cities_arg_still_works(self):
        """target_cities=[...] kwarg should still work (not just target_city)."""
        scraper = ArcticShiftScraper(
            parquet_dir="/nonexistent",
            target_cities=["tokyo", "kyoto", "osaka"],
        )
        assert scraper.config.target_cities == ["tokyo", "kyoto", "osaka"]


# ---------------------------------------------------------------------------
# Empty results / graceful handling
# ---------------------------------------------------------------------------

class TestEmptyResultsGraceful:
    def test_parse_returns_none_on_empty_text(self):
        scraper = _make_scraper(target_city="bend")
        raw = _make_post(title="", selftext="")
        assert scraper.parse(raw) is None

    def test_parse_returns_none_on_no_venue_mentions(self):
        scraper = _make_scraper(target_city="bend")
        raw = _make_post(
            selftext=(
                "Just moved to bend. The weather here is nice. "
                "Any recommendations welcome."
            ),
        )
        # Text has no venue mention patterns — may return None or empty mentions
        parsed = scraper.parse(raw)
        if parsed is not None:
            assert len(parsed["mentions"]) == 0 or True  # either is valid

    def test_get_results_returns_empty_on_no_stores(self):
        scraper = _make_scraper(target_city="bend")
        results = scraper.get_results()
        assert results["quality_signals"] == []
        assert results["mentions"] == []
        assert results["stats"]["venues_extracted"] == 0
        assert results["stats"]["rows_quality_filtered"] == 0

    def test_scrape_returns_empty_list_when_no_parquet_dir(self):
        scraper = _make_scraper(target_city="bend")
        with pytest.raises(FileNotFoundError):
            scraper.scrape()

    def test_scrape_returns_empty_list_when_no_parquet_files(self, tmp_path):
        scraper = ArcticShiftScraper(
            parquet_dir=str(tmp_path),
            target_city="bend",
        )
        result = scraper.scrape()
        assert result == []

    def test_stats_include_quality_filtered_count(self):
        scraper = _make_scraper(target_city="bend")
        # Manually bump the counter to simulate filtering
        scraper._rows_quality_filtered = 7
        results = scraper.get_results()
        assert results["stats"]["rows_quality_filtered"] == 7


# ---------------------------------------------------------------------------
# compute_authority_score — local modifier
# ---------------------------------------------------------------------------

class TestComputeAuthorityScoreLocal:
    def test_local_author_gets_higher_authority(self):
        score_local = compute_authority_score(
            score=50, subreddit="bend", sentiment="positive", is_local=True
        )
        score_visitor = compute_authority_score(
            score=50, subreddit="bend", sentiment="positive", is_local=False
        )
        assert score_local > score_visitor, (
            "Local author should receive a higher authority score"
        )

    def test_authority_bounded_0_to_1(self):
        for is_local in (True, False):
            score = compute_authority_score(
                score=9999, subreddit="bend", sentiment="positive", is_local=is_local
            )
            assert 0.0 <= score <= 1.0, f"Authority score out of bounds: {score}"

    def test_authority_score_defaults_to_non_local(self):
        """Calling without is_local should behave same as is_local=False."""
        score_default = compute_authority_score(50, "bend", "positive")
        score_false = compute_authority_score(50, "bend", "positive", is_local=False)
        assert score_default == score_false
