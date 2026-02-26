"""Tests for research bundle GCS persistence."""
import json
import pytest
from unittest.mock import MagicMock, patch
from services.api.pipeline.gcs_raw_store import (
    write_research_bundle,
    read_research_bundle,
    RESEARCH_PREFIX,
    strip_pii,
)


class TestStripPii:
    def test_strips_reddit_usernames(self):
        text = "Great rec from u/portland_foodie and u/bend-local123"
        result = strip_pii(text)
        assert "u/portland_foodie" not in result
        assert "u/bend-local123" not in result
        assert "[user]" in result

    def test_preserves_non_username_text(self):
        text = "This restaurant is amazing, you should go"
        assert strip_pii(text) == text

    def test_strips_slash_u_variant(self):
        text = "posted by /u/AnotherOne"
        result = strip_pii(text)
        assert "AnotherOne" not in result


class TestWriteResearchBundle:
    @pytest.fixture
    def mock_gcs(self):
        with patch("services.api.pipeline.gcs_raw_store._get_client") as mock:
            client = MagicMock()
            bucket = MagicMock()
            blob = MagicMock()
            blob.exists.return_value = False
            bucket.blob.return_value = blob
            client.bucket.return_value = bucket
            mock.return_value = client
            yield {"client": client, "bucket": bucket, "blob": blob}

    @pytest.mark.asyncio
    async def test_writes_jsonl_to_correct_path(self, mock_gcs):
        records = [{"source_type": "reddit_thread", "source_id": "t3_abc",
                     "title": "Test", "body": "Great food", "score": 42,
                     "upvote_ratio": 0.91, "is_local": True, "scraped_at": "2026-02-25T00:00:00"}]
        count = await write_research_bundle("bend", "reddit", records)
        assert count == 1
        mock_gcs["bucket"].blob.assert_called_with(f"{RESEARCH_PREFIX}/bend/reddit.jsonl")

    @pytest.mark.asyncio
    async def test_strips_pii_before_write(self, mock_gcs):
        records = [{"body": "rec from u/secret_user", "source_type": "reddit_thread",
                     "source_id": "t3_x", "title": "T", "score": 1,
                     "upvote_ratio": 0.5, "is_local": False, "scraped_at": "2026-02-25T00:00:00"}]
        await write_research_bundle("bend", "reddit", records)
        written = mock_gcs["blob"].upload_from_string.call_args[0][0]
        parsed = json.loads(written.decode().strip())
        assert "u/secret_user" not in parsed["body"]
        assert "[user]" in parsed["body"]

    @pytest.mark.asyncio
    async def test_appends_to_existing_blob(self, mock_gcs):
        existing = json.dumps({"source_type": "reddit_thread", "source_id": "old"}) + "\n"
        mock_gcs["blob"].exists.return_value = True
        mock_gcs["blob"].download_as_bytes.return_value = existing.encode()
        records = [{"source_type": "reddit_thread", "source_id": "new", "title": "T",
                     "body": "B", "score": 1, "upvote_ratio": 0.5,
                     "is_local": False, "scraped_at": "2026-02-25T00:00:00"}]
        await write_research_bundle("bend", "reddit", records)
        written = mock_gcs["blob"].upload_from_string.call_args[0][0].decode()
        lines = [l for l in written.strip().split("\n") if l]
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_validates_source_type(self):
        with pytest.raises(ValueError, match="source_type"):
            await write_research_bundle("bend", "invalid_type", [{"body": "x"}])

    @pytest.mark.asyncio
    async def test_gcs_failure_returns_zero(self, mock_gcs):
        mock_gcs["blob"].upload_from_string.side_effect = Exception("GCS down")
        count = await write_research_bundle("bend", "reddit", [{"source_type": "reddit_thread",
            "source_id": "t3_x", "title": "T", "body": "B", "score": 1,
            "upvote_ratio": 0.5, "is_local": False, "scraped_at": "2026-02-25T00:00:00"}])
        assert count == 0


class TestReadResearchBundle:
    @pytest.fixture
    def mock_gcs(self):
        with patch("services.api.pipeline.gcs_raw_store._get_client") as mock:
            client = MagicMock()
            bucket = MagicMock()
            blob = MagicMock()
            bucket.blob.return_value = blob
            client.bucket.return_value = bucket
            mock.return_value = client
            yield {"client": client, "bucket": bucket, "blob": blob}

    @pytest.mark.asyncio
    async def test_reads_jsonl(self, mock_gcs):
        line = json.dumps({"source_type": "reddit_thread", "source_id": "t3_abc"}) + "\n"
        mock_gcs["blob"].exists.return_value = True
        mock_gcs["blob"].download_as_bytes.return_value = line.encode()
        result = await read_research_bundle("bend", "reddit")
        assert len(result) == 1
        assert result[0]["source_id"] == "t3_abc"

    @pytest.mark.asyncio
    async def test_returns_empty_on_missing(self, mock_gcs):
        mock_gcs["blob"].exists.return_value = False
        result = await read_research_bundle("bend", "reddit")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self, mock_gcs):
        mock_gcs["blob"].exists.side_effect = Exception("GCS down")
        result = await read_research_bundle("bend", "reddit")
        assert result == []
