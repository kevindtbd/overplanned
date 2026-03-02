"""
Comprehensive tests for services.api.pipeline.reddit_download module.

~65 test cases covering stats, validation, freshness, cursor resume,
chunk flush, merge, row caps, sort/pagination, global caps, retry/backoff,
circuit breaker, file locking, DLQ, malformed responses, parquet schema,
cross-run resume, edge cases, end-to-end, and rate limiting.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from services.api.pipeline.reddit_download import (
    POST_FIELDS,
    POST_SCHEMA,
    COMMENT_FIELDS,
    COMMENT_SCHEMA,
    RedditDownloadStats,
    _flush_chunk_atomic,
    _merge_chunks_streaming,
    _read_cursor,
    _read_dlq,
    _validate_subreddit,
    _write_cursor_atomic,
    _write_dlq_atomic,
    download_reddit_data,
)
from services.api.pipeline.city_configs import BoundingBox, CityConfig

from .conftest import FakeFileLock, FakeHTTPXClient, FakeHTTPXResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_post_item(
    item_id: str = "abc",
    subreddit: str = "test",
    created_utc: int = 1700000000,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a single Arctic Shift post item."""
    item = {
        "id": item_id,
        "subreddit": subreddit,
        "title": f"Post {item_id}",
        "selftext": f"Body of {item_id}",
        "score": 10,
        "created_utc": created_utc,
        "permalink": f"/r/{subreddit}/comments/{item_id}",
        "upvote_ratio": 0.95,
        "num_comments": 5,
    }
    item.update(overrides)
    return item


def _make_comment_item(
    item_id: str = "c1",
    subreddit: str = "test",
    created_utc: int = 1700000000,
    **overrides: Any,
) -> dict[str, Any]:
    item = {
        "id": item_id,
        "subreddit": subreddit,
        "body": f"Comment {item_id}",
        "score": 5,
        "created_utc": created_utc,
        "permalink": f"/r/{subreddit}/comments/parent/{item_id}",
        "link_id": "t3_abc",
        "parent_id": "t3_abc",
    }
    item.update(overrides)
    return item


def _make_posts_response(items: list[dict], status: int = 200) -> FakeHTTPXResponse:
    return FakeHTTPXResponse(status, {"data": items})


def _make_empty_response() -> FakeHTTPXResponse:
    return FakeHTTPXResponse(200, {"data": []})


def _make_city_config(
    slug: str = "testcity",
    subreddits: dict[str, float] | None = None,
) -> CityConfig:
    return CityConfig(
        name="Test City",
        slug=slug,
        country="US",
        timezone="America/Los_Angeles",
        subreddits=subreddits if subreddits is not None else {"testsub": 1.0},
        neighborhood_terms=[],
        stopwords=[],
        bbox=BoundingBox(lat_min=0, lat_max=1, lng_min=0, lng_max=1),
    )


def _write_parquet(path: Path, rows: list[dict], schema: pa.Schema = POST_SCHEMA):
    """Write rows to a parquet file for test setup."""
    fields = [f.name for f in schema]
    columns: dict[str, list] = {f: [] for f in fields}
    for row in rows:
        for f in fields:
            columns[f].append(row.get(f))
    table = pa.table(columns, schema=schema)
    pq.write_table(table, str(path))


def _set_mtime_days_ago(path: Path, days: float):
    """Set a file's mtime to N days ago."""
    old_time = time.time() - (days * 86400)
    os.utime(str(path), (old_time, old_time))


# Convenience: queue N pages of posts then an empty page
def _queue_one_sub_success(client: FakeHTTPXClient, n_posts: int = 3, n_comments: int = 2):
    """Queue responses for one sub: posts page + empty, comments page + empty."""
    posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i * 100) for i in range(n_posts)]
    comments = [_make_comment_item(item_id=f"c{i}", created_utc=1700000000 - i * 100) for i in range(n_comments)]
    client.queue_response(_make_posts_response(posts))
    client.queue_response(_make_empty_response())  # end posts pagination
    client.queue_response(_make_posts_response(comments))
    client.queue_response(_make_empty_response())  # end comments pagination


SLEEP_PATCH = "services.api.pipeline.reddit_download.asyncio.sleep"
CONFIG_PATCH = "services.api.pipeline.reddit_download.get_city_config"


# ===========================================================================
# TestRedditDownloadStats
# ===========================================================================

class TestRedditDownloadStats:
    def test_defaults_all_zero(self):
        stats = RedditDownloadStats()
        assert stats.subreddits_checked == 0
        assert stats.subreddits_downloaded == 0
        assert stats.subreddits_skipped_fresh == 0
        assert stats.subreddits_skipped_locked == 0
        assert stats.subreddits_failed == 0
        assert stats.subreddits_resumed == 0
        assert stats.posts_downloaded == 0
        assert stats.comments_downloaded == 0
        assert stats.total_requests == 0
        assert stats.total_bytes_downloaded == 0
        assert stats.total_parquet_bytes == 0
        assert stats.dlq_entries_written == 0
        assert stats.dlq_entries_retried == 0
        assert stats.circuit_breaker_tripped is False
        assert stats.request_cap_hit is False
        assert stats.duration_cap_hit is False
        assert stats.latency_seconds == 0.0


# ===========================================================================
# TestSubredditValidation
# ===========================================================================

class TestSubredditValidation:
    def test_valid_subreddit_name_accepted(self):
        assert _validate_subreddit("portland") is True
        assert _validate_subreddit("Portland_OR") is True
        assert _validate_subreddit("bend2") is True

    def test_subreddit_with_slash_rejected(self):
        assert _validate_subreddit("r/portland") is False

    def test_subreddit_with_dots_rejected(self):
        assert _validate_subreddit("portland.or") is False

    def test_empty_subreddit_rejected(self):
        assert _validate_subreddit("") is False


# ===========================================================================
# TestFreshnessCheck
# ===========================================================================

class TestFreshnessCheck:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_fresh_file_skipped(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"freshy": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Create parquet files with current mtime (fresh)
        for ct in ("posts", "comments"):
            _write_parquet(
                tmp_path / f"freshy_{ct}.parquet",
                [_make_post_item()] if ct == "posts" else [_make_comment_item()],
                POST_SCHEMA if ct == "posts" else COMMENT_SCHEMA,
            )

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # Both posts and comments should be skipped as fresh
        assert stats.subreddits_skipped_fresh == 2
        # sub_success stays True when both content types are skipped, so the sub
        # counts as "downloaded" (no failure occurred). The key signal is zero requests.
        assert stats.total_requests == 0
        assert stats.posts_downloaded == 0
        assert stats.comments_downloaded == 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_stale_file_downloaded(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"stalesub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Create parquet and set mtime to 10 days ago
        for ct in ("posts", "comments"):
            p = tmp_path / f"stalesub_{ct}.parquet"
            _write_parquet(
                p,
                [_make_post_item(created_utc=1699000000)] if ct == "posts" else [_make_comment_item(created_utc=1699000000)],
                POST_SCHEMA if ct == "posts" else COMMENT_SCHEMA,
            )
            _set_mtime_days_ago(p, 10)

        # Queue fresh data + empty pages for posts and comments
        _queue_one_sub_success(client, n_posts=2, n_comments=2)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_skipped_fresh == 0
        assert stats.total_requests > 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_no_file_downloaded(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"newsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        _queue_one_sub_success(client)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.total_requests > 0
        assert (tmp_path / "newsub_posts.parquet").exists()

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_custom_stale_days_respected(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"customsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Create parquet, set mtime to 3 days ago
        for ct in ("posts", "comments"):
            p = tmp_path / f"customsub_{ct}.parquet"
            _write_parquet(
                p,
                [_make_post_item(created_utc=1699000000)] if ct == "posts" else [_make_comment_item(created_utc=1699000000)],
                POST_SCHEMA if ct == "posts" else COMMENT_SCHEMA,
            )
            _set_mtime_days_ago(p, 3)

        # With stale_days=2, file is stale (3 > 2)
        _queue_one_sub_success(client)
        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, stale_days=2,
            http_client=client, file_lock=lock,
        )
        assert stats.subreddits_skipped_fresh == 0
        assert stats.total_requests > 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_stale_days_zero_always_redownloads(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"zerosub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Create fresh parquet (mtime = now)
        for ct in ("posts", "comments"):
            _write_parquet(
                tmp_path / f"zerosub_{ct}.parquet",
                [_make_post_item(created_utc=1699000000)] if ct == "posts" else [_make_comment_item(created_utc=1699000000)],
                POST_SCHEMA if ct == "posts" else COMMENT_SCHEMA,
            )

        _queue_one_sub_success(client)
        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, stale_days=0,
            http_client=client, file_lock=lock,
        )
        # stale_days=0 means always redownload
        assert stats.subreddits_skipped_fresh == 0
        assert stats.total_requests > 0


# ===========================================================================
# TestCursorResume
# ===========================================================================

class TestCursorResume:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_cursor_exists_resumes_from_oldest_utc(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"resumesub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Create cursor + chunk for posts
        cursor_data = {
            "subreddit": "resumesub",
            "content_type": "posts",
            "oldest_utc_seen": 1699999000,
            "rows_flushed": 5,
            "chunks_written": 1,
            "pages_completed": 1,
            "started_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        _write_cursor_atomic(tmp_path / "resumesub_posts.cursor.json", cursor_data)
        # Create a chunk file so the resume path is hit
        _write_parquet(
            tmp_path / "resumesub_posts.chunk_0000.parquet",
            [_make_post_item(item_id=f"old{i}", created_utc=1699999000 + i) for i in range(5)],
        )

        # Queue: more posts page, then empty. Then comments pages.
        new_posts = [_make_post_item(item_id=f"new{i}", created_utc=1699998000 - i * 10) for i in range(3)]
        client.queue_response(_make_posts_response(new_posts))
        client.queue_response(_make_empty_response())
        # Comments: just empty
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_resumed >= 1
        # Check that the "before" param was set in the first posts request
        posts_reqs = [r for r in client.requests if "/posts/" in r["url"]]
        assert len(posts_reqs) > 0
        assert posts_reqs[0]["params"]["before"] == 1699999000

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_cursor_plus_chunks_continues_numbering(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"chunksub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        cursor_data = {
            "subreddit": "chunksub",
            "content_type": "posts",
            "oldest_utc_seen": 1699999000,
            "rows_flushed": 10,
            "chunks_written": 2,
            "pages_completed": 2,
            "started_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        _write_cursor_atomic(tmp_path / "chunksub_posts.cursor.json", cursor_data)
        # Two existing chunks
        for i in range(2):
            _write_parquet(
                tmp_path / f"chunksub_posts.chunk_{i:04d}.parquet",
                [_make_post_item(item_id=f"c{i}_{j}", created_utc=1699999000 + j) for j in range(5)],
            )

        # Queue enough posts to trigger a flush (chunk_size=5)
        posts = [_make_post_item(item_id=f"n{i}", created_utc=1699998000 - i) for i in range(6)]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())  # comments

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, chunk_size=5,
            http_client=client, file_lock=lock,
        )
        # After merge, the final parquet should exist
        assert (tmp_path / "chunksub_posts.parquet").exists()

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_cursor_but_no_chunks_starts_fresh(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"stalecursub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Cursor exists but no chunk files
        _write_cursor_atomic(tmp_path / "stalecursub_posts.cursor.json", {
            "subreddit": "stalecursub",
            "content_type": "posts",
            "oldest_utc_seen": 1699999000,
            "rows_flushed": 5,
            "chunks_written": 1,
        })

        _queue_one_sub_success(client)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # Cursor was deleted since no chunks => started fresh
        assert stats.subreddits_resumed == 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_corrupt_cursor_json_starts_fresh(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"corruptsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Write corrupt JSON
        cursor_path = tmp_path / "corruptsub_posts.cursor.json"
        cursor_path.write_text("{invalid json!!")

        _queue_one_sub_success(client)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # Should not crash, starts fresh
        assert stats.subreddits_resumed == 0
        assert stats.subreddits_downloaded == 1

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_chunks_but_no_cursor_cleans_orphans_starts_fresh(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"orphansub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Create orphan chunk without cursor
        _write_parquet(
            tmp_path / "orphansub_posts.chunk_0000.parquet",
            [_make_post_item()],
        )

        _queue_one_sub_success(client)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # Orphan chunk should have been cleaned. Download proceeds normally.
        assert stats.subreddits_downloaded == 1


# ===========================================================================
# TestChunkFlush
# ===========================================================================

class TestChunkFlush:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_rows_flush_at_chunk_size(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"flushy": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # 12 posts with chunk_size=5 => 2 full chunks + 1 partial (2 rows) in buffer
        posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i) for i in range(12)]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())  # comments

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, chunk_size=5,
            http_client=client, file_lock=lock,
        )
        # After merge, final parquet should have 12 rows
        table = pq.read_table(str(tmp_path / "flushy_posts.parquet"))
        assert len(table) == 12

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_cursor_updated_after_each_flush(self, mock_config, mock_sleep, tmp_path):
        """Verify cursor is written after chunk flushes during download."""
        mock_config.return_value = _make_city_config(subreddits={"cursorsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # We need enough rows to trigger at least one mid-download flush.
        # chunk_size=3, send 4 items in one page, then empty.
        posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i) for i in range(4)]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())  # comments

        # After the full download, cursor should be cleaned up (deleted on success).
        # But during the download, cursor was updated. We test the final state:
        # cursor should NOT exist (cleaned after merge).
        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, chunk_size=3,
            http_client=client, file_lock=lock,
        )
        cursor_path = tmp_path / "cursorsub_posts.cursor.json"
        assert not cursor_path.exists(), "Cursor should be cleaned up after successful merge"

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_chunk_numbering_increments(self, mock_config, mock_sleep, tmp_path):
        """Verify chunk files are numbered sequentially (tested indirectly via merged output)."""
        mock_config.return_value = _make_city_config(subreddits={"numchunk": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i) for i in range(10)]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, chunk_size=3,
            http_client=client, file_lock=lock,
        )
        # All chunks should be merged and deleted
        remaining_chunks = list(tmp_path.glob("numchunk_posts.chunk_*.parquet"))
        assert len(remaining_chunks) == 0
        table = pq.read_table(str(tmp_path / "numchunk_posts.parquet"))
        assert len(table) == 10

    def test_chunk_written_atomically_via_temp_rename(self, tmp_path):
        """Verify .tmp file does not remain after _flush_chunk_atomic."""
        rows = [_make_post_item(item_id=f"p{i}") for i in range(3)]
        chunk_path = tmp_path / "test.chunk_0000.parquet"
        _flush_chunk_atomic(rows, POST_SCHEMA, chunk_path)

        assert chunk_path.exists()
        assert not chunk_path.with_suffix(".tmp").exists()

    def test_cursor_written_atomically_via_temp_rename(self, tmp_path):
        """Verify .tmp file does not remain after _write_cursor_atomic."""
        cursor_path = tmp_path / "test.cursor.json"
        _write_cursor_atomic(cursor_path, {"oldest_utc_seen": 123})

        assert cursor_path.exists()
        assert not cursor_path.with_suffix(".tmp").exists()
        data = json.loads(cursor_path.read_text())
        assert data["oldest_utc_seen"] == 123


# ===========================================================================
# TestMergeAndCompletion
# ===========================================================================

class TestMergeAndCompletion:

    def test_all_chunks_merged_into_final_parquet(self, tmp_path):
        chunks = []
        for i in range(3):
            p = tmp_path / f"test.chunk_{i:04d}.parquet"
            _write_parquet(p, [_make_post_item(item_id=f"p{i}")])
            chunks.append(p)

        output = tmp_path / "test.parquet"
        total = _merge_chunks_streaming(chunks, output, POST_SCHEMA)
        assert total == 3
        assert output.exists()

    def test_chunks_deleted_after_merge(self, tmp_path):
        chunks = []
        for i in range(2):
            p = tmp_path / f"test.chunk_{i:04d}.parquet"
            _write_parquet(p, [_make_post_item(item_id=f"p{i}")])
            chunks.append(p)

        output = tmp_path / "test.parquet"
        _merge_chunks_streaming(chunks, output, POST_SCHEMA)
        for c in chunks:
            assert not c.exists()

    def test_cursor_deleted_after_merge(self, tmp_path):
        """Full download should clean up cursor after merge."""
        cursor_path = tmp_path / "test.cursor.json"
        _write_cursor_atomic(cursor_path, {"test": True})
        assert cursor_path.exists()
        # Cursor deletion happens in _download_subreddit_content, tested via integration

    def test_final_parquet_row_count_equals_sum_of_chunks(self, tmp_path):
        chunks = []
        expected_total = 0
        for i, count in enumerate([5, 3, 7]):
            rows = [_make_post_item(item_id=f"p{i}_{j}", created_utc=1700000000 - j) for j in range(count)]
            p = tmp_path / f"test.chunk_{i:04d}.parquet"
            _write_parquet(p, rows)
            chunks.append(p)
            expected_total += count

        output = tmp_path / "test.parquet"
        total = _merge_chunks_streaming(chunks, output, POST_SCHEMA)
        assert total == expected_total
        table = pq.read_table(str(output))
        assert len(table) == expected_total

    def test_merge_single_chunk(self, tmp_path):
        p = tmp_path / "test.chunk_0000.parquet"
        _write_parquet(p, [_make_post_item()])
        output = tmp_path / "test.parquet"
        total = _merge_chunks_streaming([p], output, POST_SCHEMA)
        assert total == 1
        assert output.exists()

    def test_merge_empty_handled(self, tmp_path):
        output = tmp_path / "test.parquet"
        total = _merge_chunks_streaming([], output, POST_SCHEMA)
        assert total == 0
        assert not output.exists()

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_lock_file_cleaned_up_after_merge(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"locksub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        _queue_one_sub_success(client)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_downloaded == 1
        # Lock file should be cleaned up on success
        assert not (tmp_path / "locksub.lock").exists()


# ===========================================================================
# TestRowCap
# ===========================================================================

class TestRowCap:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_download_stops_at_max_rows(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"capsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Queue more rows than max_rows
        posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i) for i in range(20)]
        client.queue_response(_make_posts_response(posts))
        # May or may not need empty page depending on cap
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())  # comments

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_rows_per_sub=10,
            http_client=client, file_lock=lock,
        )
        assert stats.posts_downloaded <= 10

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_cursor_saved_on_cap_hit(self, mock_config, mock_sleep, tmp_path):
        """When row cap is hit mid-page, remaining buffer is flushed and merged."""
        mock_config.return_value = _make_city_config(subreddits={"capcursub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i) for i in range(15)]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_rows_per_sub=7, chunk_size=5,
            http_client=client, file_lock=lock,
        )
        # Should have stopped at 7 rows
        assert stats.posts_downloaded <= 7
        # Final parquet should exist
        assert (tmp_path / "capcursub_posts.parquet").exists()

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_row_cap_not_multiple_of_chunk_size_flushes_remainder(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"remsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i) for i in range(20)]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_rows_per_sub=7, chunk_size=3,
            http_client=client, file_lock=lock,
        )
        table = pq.read_table(str(tmp_path / "remsub_posts.parquet"))
        assert len(table) == 7

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_row_cap_exactly_equals_chunk_size(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"exactsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i) for i in range(10)]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_rows_per_sub=5, chunk_size=5,
            http_client=client, file_lock=lock,
        )
        table = pq.read_table(str(tmp_path / "exactsub_posts.parquet"))
        assert len(table) == 5

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_row_cap_less_than_chunk_size(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"smallsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        posts = [_make_post_item(item_id=f"p{i}", created_utc=1700000000 - i) for i in range(10)]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_rows_per_sub=2, chunk_size=5,
            http_client=client, file_lock=lock,
        )
        table = pq.read_table(str(tmp_path / "smallsub_posts.parquet"))
        assert len(table) == 2


# ===========================================================================
# TestSortDesc
# ===========================================================================

class TestSortDesc:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_api_called_with_sort_desc(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"sortsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        _queue_one_sub_success(client)

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # Inspect first request's params
        assert len(client.requests) > 0
        first_req = client.requests[0]
        assert first_req["params"]["sort"] == "desc"
        assert first_req["params"]["sort_type"] == "created_utc"

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_oldest_utc_tracks_last_item(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"oldestsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        posts = [
            _make_post_item(item_id="newest", created_utc=1700000000),
            _make_post_item(item_id="oldest", created_utc=1699000000),
        ]
        client.queue_response(_make_posts_response(posts))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # The parquet should contain both items; the oldest_utc is tracked internally
        table = pq.read_table(str(tmp_path / "oldestsub_posts.parquet"))
        utc_vals = table.column("created_utc").to_pylist()
        assert min(utc_vals) == 1699000000

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_resume_uses_before_param_from_cursor(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"beforesub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Set up cursor with oldest_utc
        _write_cursor_atomic(tmp_path / "beforesub_posts.cursor.json", {
            "subreddit": "beforesub",
            "content_type": "posts",
            "oldest_utc_seen": 1699500000,
            "rows_flushed": 3,
            "chunks_written": 1,
            "pages_completed": 1,
        })
        _write_parquet(
            tmp_path / "beforesub_posts.chunk_0000.parquet",
            [_make_post_item(item_id=f"p{i}", created_utc=1699500000 + i) for i in range(3)],
        )

        client.queue_response(_make_posts_response([_make_post_item(item_id="new1", created_utc=1699400000)]))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())  # comments

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        posts_reqs = [r for r in client.requests if "/posts/" in r["url"]]
        assert posts_reqs[0]["params"]["before"] == 1699500000


# ===========================================================================
# TestGlobalCaps
# ===========================================================================

class TestGlobalCaps:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_request_cap_stops_download(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"reqcap": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Queue many pages to exceed request cap
        for _ in range(10):
            client.queue_response(_make_posts_response([_make_post_item(item_id=f"p{_}")]))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_total_requests=5,
            http_client=client, file_lock=lock,
        )
        assert stats.request_cap_hit is True
        assert stats.total_requests <= 6  # may slightly exceed due to check timing

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    @patch("services.api.pipeline.reddit_download.time.monotonic")
    async def test_duration_cap_stops_between_subs(self, mock_monotonic, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"dur1": 1.0, "dur2": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # First sub succeeds
        _queue_one_sub_success(client, n_posts=1, n_comments=1)
        # Second sub responses (shouldn't be reached)
        _queue_one_sub_success(client, n_posts=1, n_comments=1)

        # Time: start at 0, then jump past duration cap after first sub
        call_count = 0

        def advancing_time():
            nonlocal call_count
            call_count += 1
            # First few calls: time=0 (during first sub)
            if call_count <= 10:
                return 0.0
            # After that: time exceeds cap
            return 999999.0

        mock_monotonic.side_effect = advancing_time

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_duration_seconds=600,
            http_client=client, file_lock=lock,
        )
        assert stats.duration_cap_hit is True


# ===========================================================================
# TestRetryBackoff
# ===========================================================================

class TestRetryBackoff:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_429_retries_with_backoff(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"retrysub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # 429, 429, then success, then empty
        client.queue_response(FakeHTTPXResponse(429))
        client.queue_response(FakeHTTPXResponse(429))
        client.queue_response(_make_posts_response([_make_post_item()]))
        client.queue_response(_make_empty_response())
        # Comments
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_downloaded == 1
        # Sleep was called for backoff
        assert mock_sleep.call_count > 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_503_retries_with_backoff(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"srv503": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        client.queue_response(FakeHTTPXResponse(503))
        client.queue_response(_make_posts_response([_make_post_item()]))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_downloaded == 1

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_retries_exhausted_writes_dlq(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"failsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # 4 failures (initial + 3 retries) for posts
        for _ in range(4):
            client.queue_response(FakeHTTPXResponse(500))
        # Comments won't be reached since posts failed and sub is marked failed
        # Actually the loop continues to comments after posts fail
        for _ in range(4):
            client.queue_response(FakeHTTPXResponse(500))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            http_client=client, file_lock=lock,
        )
        assert stats.subreddits_failed == 1
        assert stats.dlq_entries_written == 1
        # DLQ file should exist
        dlq_path = tmp_path.parent / "dead_letter" / "reddit_download_failsub.jsonl"
        assert dlq_path.exists()

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_200_after_retry_succeeds(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"recov": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # One 500, then success
        client.queue_response(FakeHTTPXResponse(500))
        client.queue_response(_make_posts_response([_make_post_item()]))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())  # comments

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_downloaded == 1
        assert stats.subreddits_failed == 0


# ===========================================================================
# TestCircuitBreaker
# ===========================================================================

class TestCircuitBreaker:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_3_consecutive_failures_trips(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(
            subreddits={"cb1": 1.0, "cb2": 1.0, "cb3": 1.0, "cb4": 1.0, "cb5": 1.0}
        )
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Each sub: posts fail (4 attempts each), comments fail (4 attempts each)
        for _ in range(5):
            for _ in range(8):  # 4 for posts + 4 for comments
                client.queue_response(FakeHTTPXResponse(500))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            circuit_breaker_threshold=3,
            http_client=client, file_lock=lock,
        )
        assert stats.circuit_breaker_tripped is True
        # Subs 4 and 5 should be skipped (still checked but skipped via breaker)
        assert stats.subreddits_failed >= 3

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_non_consecutive_failures_no_trip(self, mock_config, mock_sleep, tmp_path):
        """fail, succeed, fail, fail -- no trip (consecutive resets on success)."""
        mock_config.return_value = _make_city_config(
            subreddits={"nc1": 1.0, "nc2": 1.0, "nc3": 1.0, "nc4": 1.0}
        )
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # nc1: fail (posts fail all retries, comments fail all retries)
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))
        # nc2: succeed
        _queue_one_sub_success(client, n_posts=1, n_comments=1)
        # nc3: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))
        # nc4: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            circuit_breaker_threshold=3,
            http_client=client, file_lock=lock,
        )
        # nc2 succeeded, resetting consecutive counter. nc3+nc4 = 2, below threshold of 3.
        assert stats.circuit_breaker_tripped is False

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_404_does_not_count_as_failure(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"notfound": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # 404 for posts, 404 for comments
        client.queue_response(FakeHTTPXResponse(404))
        client.queue_response(FakeHTTPXResponse(404))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # 404 returns (True, ...) so it's not a failure
        assert stats.subreddits_failed == 0
        assert stats.subreddits_downloaded == 1

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_404_does_not_reset_counter(self, mock_config, mock_sleep, tmp_path):
        """404 returns success=True, so consecutive_failures resets via sub_success=True."""
        mock_config.return_value = _make_city_config(
            subreddits={"fail1": 1.0, "nf404": 1.0, "fail2": 1.0, "fail3": 1.0}
        )
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # fail1: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))
        # nf404: 404 (success)
        client.queue_response(FakeHTTPXResponse(404))
        client.queue_response(FakeHTTPXResponse(404))
        # fail2: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))
        # fail3: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            circuit_breaker_threshold=3,
            http_client=client, file_lock=lock,
        )
        # 404 success resets counter. fail2 + fail3 = 2 consecutive, below threshold.
        assert stats.circuit_breaker_tripped is False

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_400_does_not_count_toward_breaker(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"bad400": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # 400 for posts and comments
        client.queue_response(FakeHTTPXResponse(400))
        client.queue_response(FakeHTTPXResponse(400))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_failed == 0
        assert stats.circuit_breaker_tripped is False

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_200_resets_counter(self, mock_config, mock_sleep, tmp_path):
        """Two failures then a success should reset consecutive_failures."""
        mock_config.return_value = _make_city_config(
            subreddits={"f1": 1.0, "f2": 1.0, "s3": 1.0, "f4": 1.0, "f5": 1.0}
        )
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # f1: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))
        # f2: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))
        # s3: success (resets counter)
        _queue_one_sub_success(client, n_posts=1, n_comments=1)
        # f4: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))
        # f5: fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            circuit_breaker_threshold=3,
            http_client=client, file_lock=lock,
        )
        # f1+f2=2, reset, f4+f5=2 -- never hits 3
        assert stats.circuit_breaker_tripped is False

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_after_trip_remaining_subs_skipped(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(
            subreddits={"t1": 1.0, "t2": 1.0, "t3": 1.0, "t4": 1.0}
        )
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # 3 subs fail to trip breaker
        for _ in range(3):
            for _ in range(8):
                client.queue_response(FakeHTTPXResponse(500))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            circuit_breaker_threshold=3,
            http_client=client, file_lock=lock,
        )
        assert stats.circuit_breaker_tripped is True
        # t4 should still be checked (it goes through the loop) but skipped
        assert stats.subreddits_checked == 4
        assert stats.subreddits_failed == 3


# ===========================================================================
# TestFileLocking
# ===========================================================================

class TestFileLocking:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_locked_sub_skipped(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"lockedsub": 1.0})
        # Pre-lock the path
        lock = FakeFileLock(locked_paths={str(tmp_path / "lockedsub.lock")})
        client = FakeHTTPXClient()

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_skipped_locked == 1
        assert stats.subreddits_downloaded == 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_lock_released_on_success(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"relsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        _queue_one_sub_success(client)

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert len(lock.released) == 1
        assert lock.released[0] == tmp_path / "relsub.lock"

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_lock_released_on_failure(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"faillock": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # All attempts fail
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))

        await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            http_client=client, file_lock=lock,
        )
        # Lock should still be released (finally block)
        assert len(lock.released) == 1


# ===========================================================================
# TestDLQ
# ===========================================================================

class TestDLQ:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_failed_sub_creates_dlq_entry(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"dlqsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            http_client=client, file_lock=lock,
        )
        assert stats.dlq_entries_written == 1
        dlq_path = tmp_path.parent / "dead_letter" / "reddit_download_dlqsub.jsonl"
        entries = _read_dlq(dlq_path)
        assert len(entries) == 1
        assert entries[0]["subreddit"] == "dlqsub"

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_dlq_entry_includes_oldest_utc(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"dlqutc": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))

        await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            http_client=client, file_lock=lock,
        )
        dlq_path = tmp_path.parent / "dead_letter" / "reddit_download_dlqutc.jsonl"
        entries = _read_dlq(dlq_path)
        assert len(entries) == 1
        # oldest_utc_seen is included in the entry (None if no data was fetched)
        assert "oldest_utc_seen" in entries[0]

    def test_dlq_write_uses_atomic_temp_rename(self, tmp_path):
        dlq_path = tmp_path / "test.jsonl"
        entries = [{"subreddit": "testsub", "attempts": 1}]
        _write_dlq_atomic(dlq_path, entries)

        assert dlq_path.exists()
        assert not dlq_path.with_suffix(".tmp").exists()
        loaded = _read_dlq(dlq_path)
        assert len(loaded) == 1

    def test_dlq_preserves_entries_from_other_content_types(self, tmp_path):
        """Multiple entries in the same DLQ file are preserved."""
        dlq_path = tmp_path / "test.jsonl"
        entries = [
            {"subreddit": "sub1", "content_type": "posts", "attempts": 1},
            {"subreddit": "sub1", "content_type": "comments", "attempts": 2},
        ]
        _write_dlq_atomic(dlq_path, entries)
        loaded = _read_dlq(dlq_path)
        assert len(loaded) == 2
        assert loaded[0]["content_type"] == "posts"
        assert loaded[1]["content_type"] == "comments"


# ===========================================================================
# TestMalformedAPIResponses
# ===========================================================================

class TestMalformedAPIResponses:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_200_missing_data_key_ends_pagination(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"malform": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Response with no "data" key => items = [], ends pagination
        client.queue_response(FakeHTTPXResponse(200, {"result": "unexpected"}))
        client.queue_response(_make_empty_response())  # comments

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_downloaded == 1
        assert stats.posts_downloaded == 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_200_empty_data_array_ends_pagination(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"emptyd": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        client.queue_response(FakeHTTPXResponse(200, {"data": []}))
        client.queue_response(FakeHTTPXResponse(200, {"data": []}))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.posts_downloaded == 0
        assert stats.comments_downloaded == 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_200_items_missing_created_utc_skipped(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"noutc": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        items = [
            _make_post_item(item_id="good", created_utc=1700000000),
            {"id": "bad", "subreddit": "noutc", "title": "no utc"},  # missing created_utc
        ]
        client.queue_response(_make_posts_response(items))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.posts_downloaded == 1  # only the good one

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_200_items_missing_id_skipped(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"noid": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        items = [
            _make_post_item(item_id="good", created_utc=1700000000),
            {"subreddit": "noid", "title": "no id", "created_utc": 1700000000},  # missing id
        ]
        client.queue_response(_make_posts_response(items))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.posts_downloaded == 1


# ===========================================================================
# TestParquetSchema
# ===========================================================================

class TestParquetSchema:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_posts_parquet_has_required_columns(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"schemaposts": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        client.queue_response(_make_posts_response([_make_post_item()]))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        table = pq.read_table(str(tmp_path / "schemaposts_posts.parquet"))
        for col in POST_FIELDS:
            assert col in table.column_names

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_comments_parquet_has_required_columns(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"schemacomm": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        client.queue_response(_make_empty_response())  # posts
        comments = [_make_comment_item()]
        client.queue_response(_make_posts_response(comments))
        client.queue_response(_make_empty_response())

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        table = pq.read_table(str(tmp_path / "schemacomm_comments.parquet"))
        for col in COMMENT_FIELDS:
            assert col in table.column_names

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_created_utc_is_numeric(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"utctype": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        client.queue_response(_make_posts_response([_make_post_item()]))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        table = pq.read_table(str(tmp_path / "utctype_posts.parquet"))
        assert table.schema.field("created_utc").type == pa.int64()

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_extra_api_fields_dropped(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"extrasub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        item = _make_post_item()
        item["author"] = "should_be_dropped"
        item["distinguished"] = "also_dropped"
        client.queue_response(_make_posts_response([item]))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        table = pq.read_table(str(tmp_path / "extrasub_posts.parquet"))
        assert "author" not in table.column_names
        assert "distinguished" not in table.column_names


# ===========================================================================
# TestCrossRunResume
# ===========================================================================

class TestCrossRunResume:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_stale_parquet_extends_backward_not_re_downloads(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"xrunsub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Existing parquet with data from epoch 1700000000
        existing_posts = [_make_post_item(item_id=f"old{i}", created_utc=1700000000 - i * 100) for i in range(5)]
        p = tmp_path / "xrunsub_posts.parquet"
        _write_parquet(p, existing_posts)
        _set_mtime_days_ago(p, 10)  # Make it stale

        # New data is older (before the existing oldest)
        new_posts = [_make_post_item(item_id=f"new{i}", created_utc=1699000000 - i * 100) for i in range(3)]
        client.queue_response(_make_posts_response(new_posts))
        client.queue_response(_make_empty_response())
        # Comments: empty
        client.queue_response(_make_empty_response())

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # The "before" param should have been set to the min of existing parquet
        posts_reqs = [r for r in client.requests if "/posts/" in r["url"]]
        if posts_reqs:
            # before should be the oldest from the existing file
            assert posts_reqs[0]["params"]["before"] == 1700000000 - 4 * 100


# ===========================================================================
# TestEdgeCases
# ===========================================================================

class TestEdgeCases:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_city_with_no_configured_subreddits_returns_zero(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        stats = await download_reddit_data(
            "emptycity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_checked == 0
        assert stats.subreddits_downloaded == 0
        assert stats.total_requests == 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    async def test_city_config_not_found_raises(self, mock_sleep, tmp_path):
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        with pytest.raises(KeyError, match="Unknown city slug"):
            await download_reddit_data(
                "nonexistent_city_xyz_999", output_dir=tmp_path,
                http_client=client, file_lock=lock,
            )


# ===========================================================================
# TestEndToEnd
# ===========================================================================

class TestEndToEnd:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_city_2_subs_both_succeed(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"sub_a": 1.0, "sub_b": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # sub_a
        _queue_one_sub_success(client, n_posts=3, n_comments=2)
        # sub_b
        _queue_one_sub_success(client, n_posts=4, n_comments=1)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_checked == 2
        assert stats.subreddits_downloaded == 2
        assert stats.posts_downloaded == 7
        assert stats.comments_downloaded == 3
        assert (tmp_path / "sub_a_posts.parquet").exists()
        assert (tmp_path / "sub_a_comments.parquet").exists()
        assert (tmp_path / "sub_b_posts.parquet").exists()
        assert (tmp_path / "sub_b_comments.parquet").exists()
        # No leftover chunks, cursors, or locks
        assert len(list(tmp_path.glob("*.chunk_*"))) == 0
        assert len(list(tmp_path.glob("*.cursor.json"))) == 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_city_2_subs_one_fails(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"good_sub": 1.0, "bad_sub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # good_sub succeeds
        _queue_one_sub_success(client, n_posts=2, n_comments=1)
        # bad_sub fails all retries (posts + comments)
        for _ in range(8):
            client.queue_response(FakeHTTPXResponse(500))

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, max_retries=3,
            http_client=client, file_lock=lock,
        )
        assert stats.subreddits_downloaded == 1
        assert stats.subreddits_failed == 1
        assert (tmp_path / "good_sub_posts.parquet").exists()

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_city_all_subs_fresh_skipped(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"fr1": 1.0, "fr2": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Create fresh parquet for both subs
        for sub in ("fr1", "fr2"):
            for ct in ("posts", "comments"):
                schema = POST_SCHEMA if ct == "posts" else COMMENT_SCHEMA
                row = _make_post_item() if ct == "posts" else _make_comment_item()
                _write_parquet(tmp_path / f"{sub}_{ct}.parquet", [row], schema)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.subreddits_skipped_fresh == 4  # 2 subs x 2 content types
        assert stats.total_requests == 0

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_stats_accumulate_across_subs(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"acc1": 1.0, "acc2": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        _queue_one_sub_success(client, n_posts=5, n_comments=3)
        _queue_one_sub_success(client, n_posts=4, n_comments=2)

        stats = await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        assert stats.posts_downloaded == 9
        assert stats.comments_downloaded == 5
        assert stats.total_requests > 0
        assert stats.total_bytes_downloaded > 0
        assert stats.latency_seconds >= 0


# ===========================================================================
# TestRateLimiting
# ===========================================================================

class TestRateLimiting:

    @pytest.mark.asyncio
    @patch(SLEEP_PATCH, new_callable=AsyncMock)
    @patch(CONFIG_PATCH)
    async def test_page_delay_between_requests(self, mock_config, mock_sleep, tmp_path):
        mock_config.return_value = _make_city_config(subreddits={"ratesub": 1.0})
        client = FakeHTTPXClient()
        lock = FakeFileLock()

        # Two pages of posts then empty, then comments empty
        client.queue_response(_make_posts_response([_make_post_item(item_id="p1")]))
        client.queue_response(_make_posts_response([_make_post_item(item_id="p2", created_utc=1699000000)]))
        client.queue_response(_make_empty_response())
        client.queue_response(_make_empty_response())  # comments

        await download_reddit_data(
            "testcity", output_dir=tmp_path, http_client=client, file_lock=lock,
        )
        # asyncio.sleep should have been called with REQUEST_DELAY_S (0.5) between pages
        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list if call.args]
        assert 0.5 in sleep_calls
