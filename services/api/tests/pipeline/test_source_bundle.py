"""Tests for source bundle assembly."""
import pytest
from services.api.pipeline.source_bundle import (
    assemble_source_bundle,
    filter_snippets_for_venues,
    check_amplification,
    SourceBundle,
    TOKEN_BUDGET,
)


def _make_reddit(source_id="t3_1", score=50, upvote_ratio=0.9, is_local=False, body="Great spot"):
    return {"source_type": "reddit_thread", "source_id": source_id,
            "title": "Test", "body": body, "score": score,
            "upvote_ratio": upvote_ratio, "is_local": is_local,
            "scraped_at": "2026-02-25T00:00:00"}


class TestAssembleSourceBundle:
    @pytest.mark.asyncio
    async def test_basic_assembly(self):
        async def reader(city, stype):
            if stype == "reddit":
                return [_make_reddit()]
            return []
        bundle = await assemble_source_bundle("bend", content_reader=reader)
        assert isinstance(bundle, SourceBundle)
        assert bundle.city_slug == "bend"
        assert bundle.token_estimate > 0

    @pytest.mark.asyncio
    async def test_filters_reddit_by_quality(self):
        async def reader(city, stype):
            if stype == "reddit":
                return [
                    _make_reddit("t3_good", score=50, upvote_ratio=0.85),
                    _make_reddit("t3_bad", score=2, upvote_ratio=0.40),
                ]
            return []
        bundle = await assemble_source_bundle("bend", content_reader=reader)
        ids = [r["source_id"] for r in bundle.reddit_top]
        assert "t3_good" in ids
        assert "t3_bad" not in ids

    @pytest.mark.asyncio
    async def test_local_threads_always_included(self):
        async def reader(city, stype):
            if stype == "reddit":
                return [_make_reddit("t3_local", score=3, upvote_ratio=0.3, is_local=True)]
            return []
        bundle = await assemble_source_bundle("bend", content_reader=reader)
        assert len(bundle.reddit_local) == 1

    @pytest.mark.asyncio
    async def test_trims_to_token_budget(self):
        long_body = "word " * 10000
        async def reader(city, stype):
            if stype == "reddit":
                return [_make_reddit(f"t3_{i}", body=long_body) for i in range(10)]
            return []
        bundle = await assemble_source_bundle("bend", content_reader=reader)
        assert bundle.token_estimate <= TOKEN_BUDGET

    @pytest.mark.asyncio
    async def test_empty_sources_produce_small_bundle(self):
        async def reader(city, stype):
            return []
        bundle = await assemble_source_bundle("bend", content_reader=reader)
        assert bundle.token_estimate < 100


class TestFilterSnippetsForVenues:
    def test_filters_to_matching_venues(self):
        snippets = [
            {"body": "Pine Tavern has amazing views", "source_id": "1"},
            {"body": "Deschutes Brewery is great", "source_id": "2"},
            {"body": "Random unrelated post", "source_id": "3"},
        ]
        result = filter_snippets_for_venues(snippets, ["Pine Tavern", "Deschutes Brewery"])
        assert len(result) == 2

    def test_case_insensitive(self):
        snippets = [{"body": "pine tavern is great", "source_id": "1"}]
        result = filter_snippets_for_venues(snippets, ["Pine Tavern"])
        assert len(result) == 1

    def test_empty_venues_returns_empty(self):
        result = filter_snippets_for_venues([{"body": "X"}], [])
        assert result == []


class TestCheckAmplification:
    def test_flags_over_threshold(self):
        snippets = [
            {"body": "Pine Tavern is great"}, {"body": "Pine Tavern again"},
            {"body": "Pine Tavern rocks"}, {"body": "Other place"}, {"body": "Another spot"},
        ]
        suspects = check_amplification(snippets, threshold=0.40)
        assert "pine tavern" in [s.lower() for s in suspects]

    def test_no_flag_under_threshold(self):
        snippets = [{"body": "Place A"}, {"body": "Place B"}, {"body": "Place C"}, {"body": "Place D"}]
        suspects = check_amplification(snippets, threshold=0.40)
        assert len(suspects) == 0
