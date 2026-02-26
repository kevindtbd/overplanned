"""
Tests for services.api.pipeline.gcs_raw_store

Covers:
- write_raw_signals_to_gcs: correct JSONL format written
- read_raw_signals_from_gcs: reads back what was written
- Append mode: second write adds to existing data, not overwrite
- Graceful degradation: GCS unavailable -> returns 0, no crash
- Empty signal list -> returns 0 without touching GCS
- write_geocoded_venues_to_gcs: correct JSONL format, dataclass and dict support
- read_geocoded_venues_from_gcs: reads back venue records
- Integration: run_llm_fallback includes GCS write step
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.api.pipeline.gcs_raw_store import (
    _blob_path,
    _decode_jsonl,
    _encode_jsonl,
    read_geocoded_venues_from_gcs,
    read_raw_signals_from_gcs,
    write_geocoded_venues_to_gcs,
    write_raw_signals_to_gcs,
)
from services.api.pipeline.llm_fallback_seeder import (
    ExtractedVenue,
    FallbackStats,
    run_llm_fallback,
)

from .conftest import FakePool, FakeRecord, make_id


# ---------------------------------------------------------------------------
# Helpers — in-memory GCS blob store
# ---------------------------------------------------------------------------


class _InMemoryBlob:
    """Simulates a single GCS blob with upload/download/exists."""

    def __init__(self, exists: bool = False, content: bytes = b""):
        self._exists = exists
        self._content = content

    def exists(self) -> bool:
        return self._exists

    def download_as_bytes(self) -> bytes:
        return self._content

    def upload_from_string(self, data: bytes, content_type: str = "") -> None:
        self._content = data
        self._exists = True


class _InMemoryBucket:
    def __init__(self):
        self._blobs: dict[str, _InMemoryBlob] = {}

    def blob(self, path: str) -> _InMemoryBlob:
        if path not in self._blobs:
            self._blobs[path] = _InMemoryBlob()
        return self._blobs[path]


class _InMemoryGCSClient:
    def __init__(self):
        self._buckets: dict[str, _InMemoryBucket] = {}

    def bucket(self, name: str) -> _InMemoryBucket:
        if name not in self._buckets:
            self._buckets[name] = _InMemoryBucket()
        return self._buckets[name]


def _make_gcs_patcher(client: _InMemoryGCSClient):
    """Return a patch context manager that injects an in-memory GCS client."""
    return patch(
        "services.api.pipeline.gcs_raw_store._get_client",
        return_value=client,
    )


# ---------------------------------------------------------------------------
# Sample data factories
# ---------------------------------------------------------------------------


def _sample_signals(n: int = 3) -> list[dict]:
    return [
        {
            "id": str(uuid.uuid4()),
            "source_name": f"Source {i}",
            "source_url": f"https://example.com/article-{i}",
            "source_authority": 0.7 + i * 0.05,
            "signal_type": "recommendation",
            "raw_excerpt": f"Excerpt number {i} about a great place in bend.",
        }
        for i in range(n)
    ]


def _sample_venues(n: int = 2) -> dict[str, ExtractedVenue]:
    return {
        f"venue-{i}-bend": ExtractedVenue(
            name=f"Venue {i}",
            category="dining",
            neighborhood="Downtown Bend",
            description=f"Description for venue {i}",
            price_level=2,
            latitude=44.058 + i * 0.001,
            longitude=-121.315 + i * 0.001,
            address=f"{100 + i} Main St, Bend OR",
            google_place_id=f"place_{i}",
        )
        for i in range(n)
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestEncodeDecodeJsonl:
    def test_roundtrip_simple(self):
        records = [{"a": 1}, {"b": "hello"}, {"c": True}]
        encoded = _encode_jsonl(records)
        decoded = _decode_jsonl(encoded)
        assert decoded == records

    def test_each_record_on_own_line(self):
        records = [{"x": 1}, {"y": 2}]
        encoded = _encode_jsonl(records)
        lines = [l for l in encoded.decode("utf-8").splitlines() if l.strip()]
        assert len(lines) == 2

    def test_unicode_preserved(self):
        records = [{"name": "Cafe de Flore \u2013 Paris"}]
        encoded = _encode_jsonl(records)
        decoded = _decode_jsonl(encoded)
        assert decoded[0]["name"] == "Cafe de Flore \u2013 Paris"

    def test_decode_skips_blank_lines(self):
        raw = b'{"a": 1}\n\n{"b": 2}\n  \n{"c": 3}\n'
        decoded = _decode_jsonl(raw)
        assert len(decoded) == 3

    def test_decode_skips_invalid_lines(self):
        raw = b'{"a": 1}\nnot-json\n{"c": 3}\n'
        decoded = _decode_jsonl(raw)
        assert len(decoded) == 2
        assert decoded[0] == {"a": 1}
        assert decoded[1] == {"c": 3}

    def test_empty_list_produces_newline(self):
        encoded = _encode_jsonl([])
        assert encoded == b"\n"

    def test_blob_path_raw(self):
        assert _blob_path("raw_places", "bend") == "raw_places/bend.jsonl"

    def test_blob_path_geo(self):
        assert _blob_path("geocoded_venues", "austin") == "geocoded_venues/austin.jsonl"


# ---------------------------------------------------------------------------
# write_raw_signals_to_gcs
# ---------------------------------------------------------------------------


class TestWriteRawSignals:
    @pytest.mark.asyncio
    async def test_writes_correct_jsonl(self):
        """Written blob decodes back to original signal records."""
        gcs = _InMemoryGCSClient()
        signals = _sample_signals(3)

        with _make_gcs_patcher(gcs):
            written = await write_raw_signals_to_gcs("bend", signals)

        assert written == 3
        bucket = gcs.bucket("overplanned-raw")
        blob = bucket.blob("raw_places/bend.jsonl")
        assert blob.exists()

        decoded = _decode_jsonl(blob.download_as_bytes())
        assert len(decoded) == 3
        assert decoded[0]["source_name"] == signals[0]["source_name"]
        assert decoded[2]["raw_excerpt"] == signals[2]["raw_excerpt"]

    @pytest.mark.asyncio
    async def test_empty_signals_returns_zero_no_write(self):
        """Empty list skips GCS entirely and returns 0."""
        gcs = _InMemoryGCSClient()

        with _make_gcs_patcher(gcs):
            written = await write_raw_signals_to_gcs("bend", [])

        assert written == 0
        # Bucket not accessed at all — blob should not exist
        bucket = gcs.bucket("overplanned-raw")
        assert not bucket.blob("raw_places/bend.jsonl").exists()

    @pytest.mark.asyncio
    async def test_custom_bucket_name(self):
        """Respects custom bucket_name parameter."""
        gcs = _InMemoryGCSClient()
        signals = _sample_signals(1)

        with _make_gcs_patcher(gcs):
            written = await write_raw_signals_to_gcs(
                "bend", signals, bucket_name="my-custom-bucket",
            )

        assert written == 1
        bucket = gcs.bucket("my-custom-bucket")
        assert bucket.blob("raw_places/bend.jsonl").exists()

    @pytest.mark.asyncio
    async def test_append_mode_does_not_overwrite(self):
        """Second write appends to existing blob, not replaces it."""
        gcs = _InMemoryGCSClient()
        first_batch = _sample_signals(2)
        second_batch = _sample_signals(3)
        # Give second batch distinct IDs so we can count them
        for s in second_batch:
            s["id"] = str(uuid.uuid4())
            s["source_name"] = "Second Source"

        with _make_gcs_patcher(gcs):
            await write_raw_signals_to_gcs("bend", first_batch)
            await write_raw_signals_to_gcs("bend", second_batch)

        bucket = gcs.bucket("overplanned-raw")
        blob = bucket.blob("raw_places/bend.jsonl")
        decoded = _decode_jsonl(blob.download_as_bytes())

        assert len(decoded) == 5  # 2 + 3
        source_names = [r["source_name"] for r in decoded]
        assert "Second Source" in source_names

    @pytest.mark.asyncio
    async def test_graceful_degradation_no_credentials(self):
        """ImportError / credentials error -> returns 0, no crash."""
        signals = _sample_signals(2)

        with patch(
            "services.api.pipeline.gcs_raw_store._get_client",
            side_effect=Exception("No credentials"),
        ):
            written = await write_raw_signals_to_gcs("bend", signals)

        assert written == 0

    @pytest.mark.asyncio
    async def test_graceful_degradation_upload_error(self):
        """Upload failure -> returns 0, no crash."""
        gcs = _InMemoryGCSClient()
        signals = _sample_signals(1)

        bad_blob = MagicMock()
        bad_blob.exists.return_value = False
        bad_blob.upload_from_string.side_effect = Exception("GCS quota exceeded")
        bad_bucket = MagicMock()
        bad_bucket.blob.return_value = bad_blob
        bad_client = MagicMock()
        bad_client.bucket.return_value = bad_bucket

        with patch(
            "services.api.pipeline.gcs_raw_store._get_client",
            return_value=bad_client,
        ):
            written = await write_raw_signals_to_gcs("bend", signals)

        assert written == 0


# ---------------------------------------------------------------------------
# read_raw_signals_from_gcs
# ---------------------------------------------------------------------------


class TestReadRawSignals:
    @pytest.mark.asyncio
    async def test_reads_back_written_signals(self):
        """Read returns exactly what was written."""
        gcs = _InMemoryGCSClient()
        signals = _sample_signals(4)

        with _make_gcs_patcher(gcs):
            await write_raw_signals_to_gcs("bend", signals)
            result = await read_raw_signals_from_gcs("bend")

        assert len(result) == 4
        assert result[0]["id"] == signals[0]["id"]

    @pytest.mark.asyncio
    async def test_missing_blob_returns_empty_list(self):
        """Returns [] when no blob exists for the city."""
        gcs = _InMemoryGCSClient()

        with _make_gcs_patcher(gcs):
            result = await read_raw_signals_from_gcs("nonexistent-city")

        assert result == []

    @pytest.mark.asyncio
    async def test_graceful_degradation_read_error(self):
        """Read failure -> returns [], no crash."""
        with patch(
            "services.api.pipeline.gcs_raw_store._get_client",
            side_effect=Exception("Network error"),
        ):
            result = await read_raw_signals_from_gcs("bend")

        assert result == []


# ---------------------------------------------------------------------------
# write_geocoded_venues_to_gcs
# ---------------------------------------------------------------------------


class TestWriteGeocodedVenues:
    @pytest.mark.asyncio
    async def test_writes_extracted_venue_dataclasses(self):
        """ExtractedVenue dataclasses are serialized correctly."""
        gcs = _InMemoryGCSClient()
        venues = _sample_venues(2)

        with _make_gcs_patcher(gcs):
            written = await write_geocoded_venues_to_gcs("bend", venues)

        assert written == 2
        bucket = gcs.bucket("overplanned-raw")
        blob = bucket.blob("geocoded_venues/bend.jsonl")
        decoded = _decode_jsonl(blob.download_as_bytes())

        assert len(decoded) == 2
        slugs = {r["slug"] for r in decoded}
        assert "venue-0-bend" in slugs
        assert "venue-1-bend" in slugs

        record = next(r for r in decoded if r["slug"] == "venue-0-bend")
        assert record["name"] == "Venue 0"
        assert record["category"] == "dining"
        assert record["latitude"] == pytest.approx(44.058, abs=1e-6)

    @pytest.mark.asyncio
    async def test_writes_plain_dict_venues(self):
        """Plain dicts are also handled correctly."""
        gcs = _InMemoryGCSClient()
        venues = {
            "my-venue-bend": {
                "name": "My Venue",
                "category": "drinks",
                "latitude": 44.059,
                "longitude": -121.316,
            }
        }

        with _make_gcs_patcher(gcs):
            written = await write_geocoded_venues_to_gcs("bend", venues)

        assert written == 1
        bucket = gcs.bucket("overplanned-raw")
        decoded = _decode_jsonl(bucket.blob("geocoded_venues/bend.jsonl").download_as_bytes())
        assert decoded[0]["slug"] == "my-venue-bend"
        assert decoded[0]["name"] == "My Venue"

    @pytest.mark.asyncio
    async def test_empty_venues_returns_zero(self):
        """Empty dict returns 0 without touching GCS."""
        gcs = _InMemoryGCSClient()

        with _make_gcs_patcher(gcs):
            written = await write_geocoded_venues_to_gcs("bend", {})

        assert written == 0

    @pytest.mark.asyncio
    async def test_append_mode(self):
        """Second write appends geocoded venues, does not replace."""
        gcs = _InMemoryGCSClient()
        venues_a = {"v0-bend": ExtractedVenue(name="V0", category="dining")}
        venues_b = {"v1-bend": ExtractedVenue(name="V1", category="drinks")}

        with _make_gcs_patcher(gcs):
            await write_geocoded_venues_to_gcs("bend", venues_a)
            await write_geocoded_venues_to_gcs("bend", venues_b)

        bucket = gcs.bucket("overplanned-raw")
        decoded = _decode_jsonl(bucket.blob("geocoded_venues/bend.jsonl").download_as_bytes())
        assert len(decoded) == 2

    @pytest.mark.asyncio
    async def test_graceful_degradation(self):
        """GCS failure -> returns 0, no crash."""
        venues = _sample_venues(1)

        with patch(
            "services.api.pipeline.gcs_raw_store._get_client",
            side_effect=Exception("No credentials"),
        ):
            written = await write_geocoded_venues_to_gcs("bend", venues)

        assert written == 0


# ---------------------------------------------------------------------------
# read_geocoded_venues_from_gcs
# ---------------------------------------------------------------------------


class TestReadGeocodedVenues:
    @pytest.mark.asyncio
    async def test_reads_back_written_venues(self):
        """Read returns the same records that were written."""
        gcs = _InMemoryGCSClient()
        venues = _sample_venues(3)

        with _make_gcs_patcher(gcs):
            await write_geocoded_venues_to_gcs("bend", venues)
            result = await read_geocoded_venues_from_gcs("bend")

        assert len(result) == 3
        slugs = {r["slug"] for r in result}
        assert "venue-0-bend" in slugs
        assert "venue-2-bend" in slugs

    @pytest.mark.asyncio
    async def test_missing_blob_returns_empty_list(self):
        gcs = _InMemoryGCSClient()

        with _make_gcs_patcher(gcs):
            result = await read_geocoded_venues_from_gcs("nowhere")

        assert result == []

    @pytest.mark.asyncio
    async def test_graceful_degradation_read_error(self):
        with patch(
            "services.api.pipeline.gcs_raw_store._get_client",
            side_effect=Exception("Timeout"),
        ):
            result = await read_geocoded_venues_from_gcs("bend")

        assert result == []


# ---------------------------------------------------------------------------
# FallbackStats GCS fields
# ---------------------------------------------------------------------------


class TestFallbackStatsGcsFields:
    def test_gcs_raw_written_defaults_to_zero(self):
        stats = FallbackStats()
        assert stats.gcs_raw_written == 0

    def test_gcs_geocoded_written_defaults_to_zero(self):
        stats = FallbackStats()
        assert stats.gcs_geocoded_written == 0

    def test_can_set_gcs_fields(self):
        stats = FallbackStats(gcs_raw_written=42, gcs_geocoded_written=7)
        assert stats.gcs_raw_written == 42
        assert stats.gcs_geocoded_written == 7


# ---------------------------------------------------------------------------
# Integration: run_llm_fallback includes GCS write steps
# ---------------------------------------------------------------------------


class TestRunLlmFallbackGcsIntegration:
    """
    Verify that run_llm_fallback calls GCS write functions at the correct
    pipeline stages. We mock both GCS functions and the LLM/DB layers.
    """

    @pytest.fixture
    def pool(self):
        return FakePool()

    def _signal_fetch_key(self) -> str:
        """
        Match the FakePool query-key logic (query.strip()[:80]) for the
        _fetch_unlinked_signals query in llm_fallback_seeder.py.
        """
        return (
            'SELECT qs.id, qs."sourceName", qs."sourceUrl", qs."sourceAuthority",\n'
            '           '
        )

    @pytest.mark.asyncio
    async def test_gcs_raw_write_called_before_llm(self, pool):
        """
        GCS raw write must be invoked after signal fetch and before LLM
        extraction. We verify it was called at all and the stat is recorded.
        """
        signal_id = make_id()
        pool._fetch_results[self._signal_fetch_key()] = [
            FakeRecord(
                id=signal_id,
                sourceName="Test Source",
                sourceUrl="https://example.com",
                sourceAuthority=0.8,
                signalType="recommendation",
                rawExcerpt="Pine Tavern in downtown Bend is worth a visit.",
            )
        ]

        mock_llm_resp = MagicMock()
        mock_llm_resp.status_code = 200
        mock_llm_resp.raise_for_status = MagicMock()
        mock_llm_resp.json.return_value = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "venues": [
                            {"name": "Pine Tavern", "category": "dining"},
                        ]
                    }),
                }
            ],
            "usage": {"input_tokens": 300, "output_tokens": 60},
        }

        call_order: list[str] = []

        async def fake_write_raw(city_slug, signals, bucket_name="overplanned-raw", project_id=""):
            call_order.append("gcs_raw")
            return len(signals)

        async def fake_write_geocoded(city_slug, venues, bucket_name="overplanned-raw", project_id=""):
            call_order.append("gcs_geocoded")
            return len(venues)

        with (
            patch(
                "services.api.pipeline.llm_fallback_seeder.write_raw_signals_to_gcs",
                side_effect=fake_write_raw,
            ),
            patch(
                "services.api.pipeline.llm_fallback_seeder.write_geocoded_venues_to_gcs",
                side_effect=fake_write_geocoded,
            ),
            patch("services.api.pipeline.llm_fallback_seeder.httpx.AsyncClient") as MockClient,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_llm_resp
            mock_client.get.return_value = MagicMock(
                status_code=200,
                raise_for_status=MagicMock(),
                json=MagicMock(return_value={"places": []}),
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            stats = await run_llm_fallback(pool, "bend", api_key="test-key")

        assert stats.gcs_raw_written == 1
        assert stats.gcs_geocoded_written == 1
        # raw must come before geocoded
        assert call_order.index("gcs_raw") < call_order.index("gcs_geocoded")

    @pytest.mark.asyncio
    async def test_gcs_failure_does_not_abort_pipeline(self, pool):
        """
        Even if both GCS writes fail (graceful degradation), the pipeline
        must complete successfully and return valid stats.
        """
        signal_id = make_id()
        pool._fetch_results[self._signal_fetch_key()] = [
            FakeRecord(
                id=signal_id,
                sourceName="Blog",
                sourceUrl="https://blog.example.com",
                sourceAuthority=0.75,
                signalType="recommendation",
                rawExcerpt="Deschutes Brewery is a must-visit in Bend.",
            )
        ]

        mock_llm_resp = MagicMock()
        mock_llm_resp.status_code = 200
        mock_llm_resp.raise_for_status = MagicMock()
        mock_llm_resp.json.return_value = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "venues": [
                            {"name": "Deschutes Brewery", "category": "drinks"},
                        ]
                    }),
                }
            ],
            "usage": {"input_tokens": 200, "output_tokens": 50},
        }

        async def failing_write(*args, **kwargs) -> int:
            raise Exception("GCS unavailable")

        with (
            patch(
                "services.api.pipeline.llm_fallback_seeder.write_raw_signals_to_gcs",
                side_effect=failing_write,
            ),
            patch(
                "services.api.pipeline.llm_fallback_seeder.write_geocoded_venues_to_gcs",
                side_effect=failing_write,
            ),
            patch("services.api.pipeline.llm_fallback_seeder.httpx.AsyncClient") as MockClient,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_llm_resp
            mock_client.get.return_value = MagicMock(
                status_code=200,
                raise_for_status=MagicMock(),
                json=MagicMock(return_value={"places": []}),
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            # Should not raise despite GCS failures
            stats = await run_llm_fallback(pool, "bend", api_key="test-key")

        # GCS failed but pipeline finished
        assert stats.signals_fetched == 1
        assert stats.venues_extracted == 1
        assert stats.errors == []

    @pytest.mark.asyncio
    async def test_gcs_write_not_called_when_no_signals(self, pool):
        """
        When there are no unlinked signals, GCS write must not be called
        (early return before step 1a).
        """
        # pool returns empty list (default FakePool behaviour)
        with (
            patch(
                "services.api.pipeline.llm_fallback_seeder.write_raw_signals_to_gcs",
            ) as mock_raw,
            patch(
                "services.api.pipeline.llm_fallback_seeder.write_geocoded_venues_to_gcs",
            ) as mock_geo,
        ):
            stats = await run_llm_fallback(pool, "bend", api_key="test-key")

        assert stats.signals_fetched == 0
        mock_raw.assert_not_called()
        mock_geo.assert_not_called()

    @pytest.mark.asyncio
    async def test_custom_gcs_bucket_passed_through(self, pool):
        """gcs_bucket param is forwarded to the GCS write functions."""
        signal_id = make_id()
        pool._fetch_results[self._signal_fetch_key()] = [
            FakeRecord(
                id=signal_id,
                sourceName="Test",
                sourceUrl="https://x.com",
                sourceAuthority=0.6,
                signalType="mention",
                rawExcerpt="Pine Tavern in downtown Bend.",
            )
        ]

        mock_llm_resp = MagicMock()
        mock_llm_resp.status_code = 200
        mock_llm_resp.raise_for_status = MagicMock()
        mock_llm_resp.json.return_value = {
            "content": [{"type": "text", "text": json.dumps({"venues": []})}],
            "usage": {"input_tokens": 100, "output_tokens": 20},
        }

        received_buckets: list[str] = []

        async def capture_bucket(city_slug, data, bucket_name="overplanned-raw", project_id=""):
            received_buckets.append(bucket_name)
            return len(data) if isinstance(data, list) else len(data)

        with (
            patch(
                "services.api.pipeline.llm_fallback_seeder.write_raw_signals_to_gcs",
                side_effect=capture_bucket,
            ),
            patch(
                "services.api.pipeline.llm_fallback_seeder.write_geocoded_venues_to_gcs",
                side_effect=capture_bucket,
            ),
            patch("services.api.pipeline.llm_fallback_seeder.httpx.AsyncClient") as MockClient,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_llm_resp
            mock_client.get.return_value = MagicMock(
                status_code=200,
                raise_for_status=MagicMock(),
                json=MagicMock(return_value={"places": []}),
            )
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            await run_llm_fallback(
                pool, "bend", api_key="test-key", gcs_bucket="my-test-bucket",
            )

        for bucket in received_buckets:
            assert bucket == "my-test-bucket", f"Expected my-test-bucket, got {bucket}"
