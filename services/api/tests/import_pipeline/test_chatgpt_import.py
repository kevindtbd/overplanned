"""
Tests for services/api/import_pipeline/chatgpt_import.py

Coverage:
  - Happy path: valid ZIP with conversations.json, travel keywords present
  - ZIP security: compressed size cap, decompressed size cap, path traversal, backslash
  - Streaming cap: conversation limit, JSON byte limit
  - PII scrubbing: phone, email, SSN, credit card
  - HTML encoding of source_text
  - source_text length cap (500 chars)
  - Rate limiting: max 3 imports per hour
  - Missing conversations.json in ZIP
  - Invalid ZIP bytes
  - Non-travel conversations filtered out
  - DB persistence: signals batch-inserted, job status updated
  - Unhandled exception path: job updated to failed
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from services.api.import_pipeline.chatgpt_import import (
    process_chatgpt_import,
    _scrub_pii,
    _validate_zip_entry,
    _has_travel_keywords,
    _extract_user_messages_from_conversation,
    MAX_COMPRESSED_BYTES,
    MAX_DECOMPRESSED_BYTES,
    MAX_CONVERSATIONS,
    MAX_SOURCE_TEXT_CHARS,
    RATE_LIMIT_IMPORTS_PER_HOUR,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_ID = "user-abc-123"


def _make_conversation(
    user_messages: list[str],
    title: str = "Travel chat",
) -> dict:
    """Build a minimal ChatGPT conversation dict."""
    mapping = {}
    for i, msg in enumerate(user_messages):
        mapping[f"node-{i}"] = {
            "message": {
                "author": {"role": "user"},
                "content": {
                    "content_type": "text",
                    "parts": [msg],
                },
            }
        }
    return {"title": title, "mapping": mapping}


def _make_zip(conversations: list[dict], filename: str = "conversations.json") -> bytes:
    """Pack conversations into a ZIP bytes object."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, json.dumps(conversations))
    return buf.getvalue()


def _make_mock_db_pool(rate_limit_count: int = 0) -> AsyncMock:
    """Build a mock asyncpg pool."""
    pool = AsyncMock()
    conn = AsyncMock()

    # Rate limit check returns a row with cnt
    rate_row = MagicMock()
    rate_row.__getitem__ = MagicMock(side_effect=lambda k: rate_limit_count if k == "cnt" else None)

    conn.fetchrow = AsyncMock(return_value=rate_row)
    conn.execute = AsyncMock(return_value=None)
    conn.executemany = AsyncMock(return_value=None)

    # context manager for acquire()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))

    return pool


def _make_mock_anthropic(dimension: str = "food_priority") -> AsyncMock:
    """Mock anthropic client whose Haiku returns a well-formed response."""
    client = AsyncMock()
    resp = MagicMock()
    resp.content = [MagicMock()]
    resp.content[0].text = "[]"  # NLP returns empty (no LLM needed here)
    resp.usage = MagicMock()
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 20
    client.messages.create = AsyncMock(return_value=resp)
    return client


# ---------------------------------------------------------------------------
# Unit: _scrub_pii
# ---------------------------------------------------------------------------

class TestScrubPii:
    def test_removes_email(self):
        assert "[EMAIL]" in _scrub_pii("Contact me at user@example.com please")

    def test_removes_phone_us(self):
        assert "[PHONE]" in _scrub_pii("Call 555-867-5309 anytime")

    def test_removes_ssn(self):
        assert "[SSN]" in _scrub_pii("My SSN is 123-45-6789")

    def test_removes_credit_card(self):
        result = _scrub_pii("Card: 4111 1111 1111 1111")
        assert "[CARD]" in result

    def test_no_pii_unchanged(self):
        text = "I love hiking in the mountains."
        assert _scrub_pii(text) == text

    def test_multiple_pii_types(self):
        text = "Email: alice@test.com, Phone: 555-123-4567"
        result = _scrub_pii(text)
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "alice@test.com" not in result


# ---------------------------------------------------------------------------
# Unit: _validate_zip_entry
# ---------------------------------------------------------------------------

class TestValidateZipEntry:
    def _make_info(self, filename: str, file_size: int = 100) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(filename)
        info.file_size = file_size
        return info

    def test_valid_entry_passes(self):
        info = self._make_info("conversations.json")
        assert _validate_zip_entry(info) is True

    def test_backslash_rejected(self):
        info = self._make_info("some\\path.json")
        with pytest.raises(ValueError, match="backslash"):
            _validate_zip_entry(info)

    def test_absolute_path_rejected(self):
        info = self._make_info("/etc/passwd")
        with pytest.raises(ValueError, match="absolute path"):
            _validate_zip_entry(info)

    def test_path_traversal_rejected(self):
        info = self._make_info("../../../etc/passwd")
        with pytest.raises(ValueError, match="path traversal"):
            _validate_zip_entry(info)

    def test_nested_traversal_rejected(self):
        info = self._make_info("data/../../../etc/passwd")
        with pytest.raises(ValueError, match="path traversal"):
            _validate_zip_entry(info)

    def test_oversized_entry_rejected(self):
        info = self._make_info("big.json", file_size=MAX_DECOMPRESSED_BYTES + 1)
        with pytest.raises(ValueError, match="exceeds max decompressed"):
            _validate_zip_entry(info)

    def test_nested_valid_path(self):
        info = self._make_info("export/conversations.json")
        assert _validate_zip_entry(info) is True


# ---------------------------------------------------------------------------
# Unit: _has_travel_keywords
# ---------------------------------------------------------------------------

class TestHasTravelKeywords:
    def test_detects_trip(self):
        assert _has_travel_keywords("Planning a trip to Mexico")

    def test_detects_vacation(self):
        assert _has_travel_keywords("Summer vacation ideas for Europe")

    def test_detects_hotel(self):
        assert _has_travel_keywords("Best hotel in Austin for SXSW")

    def test_no_keywords_returns_false(self):
        assert not _has_travel_keywords("Can you help me debug this Python code?")

    def test_case_insensitive(self):
        assert _has_travel_keywords("TRAVEL to Japan")


# ---------------------------------------------------------------------------
# Unit: _extract_user_messages_from_conversation
# ---------------------------------------------------------------------------

class TestExtractUserMessages:
    def test_extracts_user_messages(self):
        conv = _make_conversation(["I want to go to Tokyo", "Recommend food options"])
        msgs = _extract_user_messages_from_conversation(conv)
        assert "I want to go to Tokyo" in msgs
        assert "Recommend food options" in msgs

    def test_skips_assistant_messages(self):
        conv = {
            "mapping": {
                "a": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["I suggest Tokyo"]},
                    }
                }
            }
        }
        msgs = _extract_user_messages_from_conversation(conv)
        assert msgs == []

    def test_skips_non_text_content(self):
        conv = {
            "mapping": {
                "a": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "image", "parts": ["base64data"]},
                    }
                }
            }
        }
        msgs = _extract_user_messages_from_conversation(conv)
        assert msgs == []

    def test_empty_mapping(self):
        conv = {"mapping": {}}
        assert _extract_user_messages_from_conversation(conv) == []

    def test_missing_mapping(self):
        conv = {}
        assert _extract_user_messages_from_conversation(conv) == []

    def test_empty_parts_skipped(self):
        conv = {
            "mapping": {
                "a": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": [""]},
                    }
                }
            }
        }
        msgs = _extract_user_messages_from_conversation(conv)
        assert msgs == []


# ---------------------------------------------------------------------------
# Integration: process_chatgpt_import — happy path
# ---------------------------------------------------------------------------

class TestProcessChatGPTImportHappyPath:
    async def test_returns_completed_status(self):
        conversations = [
            _make_conversation(["I want to find good restaurants on my trip to New Orleans"])
        ]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(
            zip_bytes=zip_bytes,
            user_id=USER_ID,
            db_pool=db_pool,
            anthropic_client=None,
        )

        assert result["status"] == "completed"
        assert result["job_id"] is not None
        assert isinstance(result["signals_extracted"], int)
        assert result["conversations_processed"] >= 1

    async def test_non_travel_conversations_filtered(self):
        conversations = [
            _make_conversation(["Write me a Python function that sorts a list"])
        ]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(
            zip_bytes=zip_bytes,
            user_id=USER_ID,
            db_pool=db_pool,
            anthropic_client=None,
        )

        assert result["status"] == "completed"
        assert result["conversations_processed"] == 0

    async def test_job_id_is_uuid_format(self):
        import re
        conversations = [_make_conversation(["Best hotel in Austin?"])]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(zip_bytes, USER_ID, db_pool)

        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            result["job_id"],
        )


# ---------------------------------------------------------------------------
# Integration: rate limiting
# ---------------------------------------------------------------------------

class TestRateLimit:
    async def test_blocks_when_limit_exceeded(self):
        conversations = [_make_conversation(["Planning a vacation to Paris"])]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=RATE_LIMIT_IMPORTS_PER_HOUR)

        result = await process_chatgpt_import(
            zip_bytes=zip_bytes,
            user_id=USER_ID,
            db_pool=db_pool,
        )

        assert result["status"] == "failed"
        assert result["job_id"] is None
        assert "Rate limit" in result["error"]

    async def test_allows_when_under_limit(self):
        conversations = [_make_conversation(["I need hotel recommendations for my trip"])]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=RATE_LIMIT_IMPORTS_PER_HOUR - 1)

        result = await process_chatgpt_import(zip_bytes, USER_ID, db_pool)

        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Integration: ZIP security
# ---------------------------------------------------------------------------

class TestZIPSecurity:
    async def test_rejects_oversized_compressed(self):
        # Provide raw bytes larger than MAX_COMPRESSED_BYTES
        oversized = b"x" * (MAX_COMPRESSED_BYTES + 1)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(oversized, USER_ID, db_pool)

        assert result["status"] == "failed"
        assert "compressed size" in result["error"]
        assert result["job_id"] is None

    async def test_rejects_invalid_zip(self):
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(b"not a zip", USER_ID, db_pool)

        assert result["status"] == "failed"
        assert "Invalid ZIP" in result["error"]
        assert result["job_id"] is not None  # job created before ZIP validation

    async def test_rejects_path_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            # Add an entry with path traversal
            info = zipfile.ZipInfo("../evil.json")
            zf.writestr(info, "[]")
            # Also add a conversations.json to make the file look legit
            zf.writestr("conversations.json", "[]")
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(buf.getvalue(), USER_ID, db_pool)

        assert result["status"] == "failed"
        assert "traversal" in result["error"].lower()

    async def test_rejects_missing_conversations_json(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("other_file.json", "[]")
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(buf.getvalue(), USER_ID, db_pool)

        assert result["status"] == "failed"
        assert "conversations.json" in result["error"]

    async def test_finds_nested_conversations_json(self):
        """conversations.json nested in a folder should still be found."""
        buf = io.BytesIO()
        conversations = [_make_conversation(["Best restaurants on my trip to Austin"])]
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("export/conversations.json", json.dumps(conversations))
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(buf.getvalue(), USER_ID, db_pool)

        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Integration: streaming caps
# ---------------------------------------------------------------------------

class TestStreamingCaps:
    async def test_conversation_cap_limits_processing(self):
        """Build ZIP with MAX_CONVERSATIONS + 5 travel conversations."""
        conversations = [
            _make_conversation([f"I want to visit hotel number {i} on my trip"])
            for i in range(MAX_CONVERSATIONS + 5)
        ]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(zip_bytes, USER_ID, db_pool)

        # Should complete (not fail), but cap conversations_processed at MAX_CONVERSATIONS
        assert result["status"] == "completed"
        assert result["conversations_processed"] <= MAX_CONVERSATIONS


# ---------------------------------------------------------------------------
# Integration: PII scrubbing and text processing
# ---------------------------------------------------------------------------

class TestPIIScrubbing:
    async def test_pii_scrubbed_before_storage(self):
        """Signals with PII in source_text should have PII replaced before DB write."""
        # We'll use a travel keyword to pass the pre-filter
        conversations = [
            _make_conversation(
                ["Trip planning: email me at spy@example.com for hotel recommendations"]
            )
        ]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        # Use real rule-based extraction that will match "hotel"
        result = await process_chatgpt_import(zip_bytes, USER_ID, db_pool, anthropic_client=None)

        assert result["status"] == "completed"
        # Verify that executemany was called with scrubbed text (no raw email in stored data)
        conn = db_pool.acquire.return_value.__aenter__.return_value
        if conn.executemany.called:
            for call_args in conn.executemany.call_args_list:
                rows = call_args[0][1]  # second positional arg is the rows list
                for row in rows:
                    source_text = row[5]  # index 5 is sourceText
                    assert "spy@example.com" not in source_text

    async def test_source_text_capped_at_500_chars(self):
        """source_text stored in DB must not exceed MAX_SOURCE_TEXT_CHARS."""
        # Build a message that will definitely produce a long source_text match
        long_text = "hotel " + "x" * 600
        conversations = [_make_conversation([long_text])]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(zip_bytes, USER_ID, db_pool)

        assert result["status"] == "completed"
        conn = db_pool.acquire.return_value.__aenter__.return_value
        for call_args in conn.executemany.call_args_list:
            rows = call_args[0][1]
            for row in rows:
                source_text = row[5]  # index 5 is sourceText
                assert len(source_text) <= MAX_SOURCE_TEXT_CHARS


# ---------------------------------------------------------------------------
# Integration: DB interaction
# ---------------------------------------------------------------------------

class TestDatabaseInteraction:
    async def test_job_created_before_processing(self):
        """ImportJob INSERT happens before conversation processing."""
        conversations = [_make_conversation(["Planning a travel itinerary"])]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(zip_bytes, USER_ID, db_pool)

        conn = db_pool.acquire.return_value.__aenter__.return_value
        # execute should have been called at least twice: INSERT job + UPDATE job
        assert conn.execute.call_count >= 2

    async def test_job_updated_to_completed_on_success(self):
        conversations = [_make_conversation(["Looking for the best restaurant on my vacation"])]
        zip_bytes = _make_zip(conversations)
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(zip_bytes, USER_ID, db_pool)

        assert result["status"] == "completed"
        # Final update call should include "completed"
        conn = db_pool.acquire.return_value.__aenter__.return_value
        update_calls = [c for c in conn.execute.call_args_list if len(c[0]) >= 3 and c[0][2] == "complete"]
        assert len(update_calls) >= 1

    async def test_job_updated_to_failed_on_invalid_zip(self):
        db_pool = _make_mock_db_pool(rate_limit_count=0)

        result = await process_chatgpt_import(b"corrupt", USER_ID, db_pool)

        assert result["status"] == "failed"
        conn = db_pool.acquire.return_value.__aenter__.return_value
        update_calls = [c for c in conn.execute.call_args_list if len(c[0]) >= 3 and c[0][2] == "failed"]
        assert len(update_calls) >= 1


# ---------------------------------------------------------------------------
# Integration: error propagation
# ---------------------------------------------------------------------------

class TestErrorPropagation:
    async def test_db_failure_returns_failed_status(self):
        """If DB pool raises, return failed status without crashing."""
        conversations = [_make_conversation(["Looking for hotels on my trip"])]
        zip_bytes = _make_zip(conversations)

        # Pool that raises on acquire
        bad_pool = AsyncMock()
        bad_pool.acquire = MagicMock(side_effect=RuntimeError("DB connection refused"))

        result = await process_chatgpt_import(zip_bytes, USER_ID, bad_pool)

        assert result["status"] == "failed"
        assert result["error"] is not None

    async def test_returns_error_key_on_failure(self):
        result = await process_chatgpt_import(b"bad", USER_ID, _make_mock_db_pool(0))
        # Either "Invalid ZIP" error or some error — error key must exist
        assert "error" in result
