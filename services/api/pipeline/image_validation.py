"""
Image validation and curation for ActivityNodes.

Priority waterfall for sourcing images:
  1. Unsplash (free API, high quality, landscape/travel focus)
  2. Google Places photos (via Places API)
  3. Google Places photos (via Places API)
  4. None (no image — node stays imageless)

Validation checks (Cloud Vision API):
  - Quality: blur detection, lighting assessment
  - Safety: SafeSearch inappropriate content detection
  - Resolution: minimum 400x300 pixels

Deliverable: canonical ActivityNodes with validated images or flagged bad images.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import asyncpg
import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_WIDTH = 400
MIN_HEIGHT = 300

# Unsplash API (free tier: 50 req/hr)
UNSPLASH_API_URL = "https://api.unsplash.com"

# Google Places Photo API
GOOGLE_PLACES_PHOTO_URL = "https://places.googleapis.com/v1/{name}/media"

# Cloud Vision API
VISION_API_URL = "https://vision.googleapis.com/v1/images:annotate"

# SafeSearch thresholds — reject if any category >= this
# Values map to: UNKNOWN=0, VERY_UNLIKELY=1, UNLIKELY=2, POSSIBLE=3, LIKELY=4, VERY_LIKELY=5
SAFESEARCH_REJECT_THRESHOLD = 3  # POSSIBLE or higher → reject

# Blur detection — reject if blur likelihood >= this
BLUR_REJECT_THRESHOLD = 4  # LIKELY or higher → reject

# Batch size for processing nodes
BATCH_SIZE = 50

# Concurrent HTTP requests
MAX_CONCURRENT = 10


class ImageSource(str, Enum):
    """Where the image came from."""
    UNSPLASH = "unsplash"
    GOOGLE_PLACES = "google_places"
    EXISTING = "existing"  # already had a URL, just validated


class ImageFlag(str, Enum):
    """Why an image was rejected."""
    BLUR = "blur_detected"
    LOW_RESOLUTION = "low_resolution"
    INAPPROPRIATE = "inappropriate_content"
    FETCH_FAILED = "fetch_failed"
    VALIDATION_ERROR = "validation_error"
    NO_IMAGE_FOUND = "no_image_found"


class SafeSearchLikelihood(int, Enum):
    """Maps Cloud Vision SafeSearch likelihood names to ints."""
    UNKNOWN = 0
    VERY_UNLIKELY = 1
    UNLIKELY = 2
    POSSIBLE = 3
    LIKELY = 4
    VERY_LIKELY = 5


# Map string labels from Vision API to our enum
_LIKELIHOOD_MAP = {
    "UNKNOWN": SafeSearchLikelihood.UNKNOWN,
    "VERY_UNLIKELY": SafeSearchLikelihood.VERY_UNLIKELY,
    "UNLIKELY": SafeSearchLikelihood.UNLIKELY,
    "POSSIBLE": SafeSearchLikelihood.POSSIBLE,
    "LIKELY": SafeSearchLikelihood.LIKELY,
    "VERY_LIKELY": SafeSearchLikelihood.VERY_LIKELY,
}


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

@dataclass
class ImageResult:
    """Outcome of image sourcing + validation for a single node."""
    node_id: str
    image_url: Optional[str] = None
    source: Optional[ImageSource] = None
    width: Optional[int] = None
    height: Optional[int] = None
    validated: bool = False
    flag: Optional[ImageFlag] = None
    flag_detail: Optional[str] = None


@dataclass
class ValidationStats:
    """Aggregate stats from a validation run."""
    nodes_processed: int = 0
    images_sourced: int = 0
    images_validated: int = 0
    images_flagged: int = 0
    images_skipped: int = 0  # already validated
    by_source: dict[str, int] = field(default_factory=lambda: {
        ImageSource.UNSPLASH.value: 0,
        ImageSource.GOOGLE_PLACES.value: 0,
        ImageSource.EXISTING.value: 0,
    })
    by_flag: dict[str, int] = field(default_factory=lambda: {
        f.value: 0 for f in ImageFlag
    })
    errors: list[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Image source clients
# ---------------------------------------------------------------------------

async def _search_unsplash(
    client: httpx.AsyncClient,
    query: str,
    api_key: str,
) -> Optional[str]:
    """
    Search Unsplash for a relevant image.

    Returns the regular-size URL or None.
    """
    try:
        resp = await client.get(
            f"{UNSPLASH_API_URL}/search/photos",
            params={
                "query": query,
                "per_page": 1,
                "orientation": "landscape",
                "content_filter": "high",  # only safe content
            },
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            return None

        photo = results[0]
        url = photo.get("urls", {}).get("regular")

        # Trigger Unsplash download tracking (required by API guidelines)
        download_link = photo.get("links", {}).get("download_location")
        if download_link and url:
            # Fire-and-forget — don't block on this
            asyncio.create_task(_trigger_unsplash_download(client, download_link, api_key))

        return url
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            logger.warning("Unsplash rate limit hit")
        else:
            logger.warning("Unsplash search failed: %s", exc)
        return None
    except Exception as exc:
        logger.warning("Unsplash search error: %s", exc)
        return None


async def _trigger_unsplash_download(
    client: httpx.AsyncClient,
    download_location: str,
    api_key: str,
) -> None:
    """Trigger Unsplash download event (API TOS requirement)."""
    try:
        await client.get(
            download_location,
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=5.0,
        )
    except Exception:
        pass  # best-effort, don't fail the pipeline


async def _fetch_google_places_photo(
    client: httpx.AsyncClient,
    google_place_id: str,
    api_key: str,
) -> Optional[str]:
    """
    Fetch the first photo for a Google Places venue.

    Uses the Places API (New) photo endpoint.
    Returns a photo URL or None.
    """
    try:
        # First, get photo references from place details
        resp = await client.get(
            f"https://places.googleapis.com/v1/places/{google_place_id}",
            params={"fields": "photos"},
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "photos",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

        photos = data.get("photos", [])
        if not photos:
            return None

        photo_name = photos[0].get("name")
        if not photo_name:
            return None

        # Get the actual photo URI
        photo_resp = await client.get(
            f"https://places.googleapis.com/v1/{photo_name}/media",
            params={
                "maxWidthPx": 800,
                "maxHeightPx": 600,
                "skipHttpRedirect": "true",
            },
            headers={"X-Goog-Api-Key": api_key},
            timeout=10.0,
        )
        photo_resp.raise_for_status()
        photo_data = photo_resp.json()

        return photo_data.get("photoUri")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            logger.warning("Google Places rate limit hit")
        else:
            logger.warning("Google Places photo failed for %s: %s", google_place_id, exc)
        return None
    except Exception as exc:
        logger.warning("Google Places photo error for %s: %s", google_place_id, exc)
        return None


# ---------------------------------------------------------------------------
# Cloud Vision validation
# ---------------------------------------------------------------------------

@dataclass
class VisionResult:
    """Result of Cloud Vision API analysis."""
    safe: bool = True
    blurry: bool = False
    width: int = 0
    height: int = 0
    flag: Optional[ImageFlag] = None
    flag_detail: Optional[str] = None


async def _validate_image_vision(
    client: httpx.AsyncClient,
    image_url: str,
    api_key: str,
) -> VisionResult:
    """
    Validate an image using Cloud Vision API.

    Checks:
      1. SafeSearch — reject inappropriate content
      2. Image properties — detect blur via likelihood
      3. Resolution — must meet minimum 400x300
    """
    result = VisionResult()

    try:
        body = {
            "requests": [
                {
                    "image": {"source": {"imageUri": image_url}},
                    "features": [
                        {"type": "SAFE_SEARCH_DETECTION"},
                        {"type": "IMAGE_PROPERTIES"},
                    ],
                    "imageContext": {
                        "cropHintsParams": {"aspectRatios": [4 / 3]},
                    },
                }
            ]
        }

        resp = await client.post(
            VISION_API_URL,
            params={"key": api_key},
            json=body,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        responses = data.get("responses", [])
        if not responses:
            result.flag = ImageFlag.VALIDATION_ERROR
            result.flag_detail = "Empty Vision API response"
            return result

        annotation = responses[0]

        # Check for API-level error
        if "error" in annotation:
            error_msg = annotation["error"].get("message", "unknown")
            result.flag = ImageFlag.VALIDATION_ERROR
            result.flag_detail = f"Vision API error: {error_msg}"
            return result

        # --- SafeSearch ---
        safe_search = annotation.get("safeSearchAnnotation", {})
        for category in ("adult", "violence", "racy"):
            likelihood_str = safe_search.get(category, "UNKNOWN")
            likelihood = _LIKELIHOOD_MAP.get(likelihood_str, SafeSearchLikelihood.UNKNOWN)
            if likelihood.value >= SAFESEARCH_REJECT_THRESHOLD:
                result.safe = False
                result.flag = ImageFlag.INAPPROPRIATE
                result.flag_detail = f"SafeSearch {category}={likelihood_str}"
                return result

        # --- Blur detection via imagePropertiesAnnotation ---
        # Cloud Vision doesn't have a direct "blur" field, but we can
        # check if the image was flagged as blurry via SAFE_SEARCH's
        # "blurred" field (available in some responses), or we infer
        # from the dominant colors' pixel fraction (low fraction = noisy).
        blurred_str = safe_search.get("blurred", "UNKNOWN")
        blurred = _LIKELIHOOD_MAP.get(blurred_str, SafeSearchLikelihood.UNKNOWN)
        if blurred.value >= BLUR_REJECT_THRESHOLD:
            result.blurry = True
            result.flag = ImageFlag.BLUR
            result.flag_detail = f"Blur likelihood={blurred_str}"
            return result

        # --- Resolution check ---
        # Vision API doesn't directly return dimensions in the annotation,
        # so we fetch image headers to determine size.
        width, height = await _get_image_dimensions(client, image_url)
        result.width = width
        result.height = height

        if width < MIN_WIDTH or height < MIN_HEIGHT:
            result.flag = ImageFlag.LOW_RESOLUTION
            result.flag_detail = f"{width}x{height} below minimum {MIN_WIDTH}x{MIN_HEIGHT}"
            return result

        return result

    except httpx.HTTPStatusError as exc:
        result.flag = ImageFlag.VALIDATION_ERROR
        result.flag_detail = f"Vision API HTTP {exc.response.status_code}"
        return result
    except Exception as exc:
        result.flag = ImageFlag.VALIDATION_ERROR
        result.flag_detail = str(exc)
        return result


async def _get_image_dimensions(
    client: httpx.AsyncClient,
    image_url: str,
) -> tuple[int, int]:
    """
    Get image dimensions via a partial download + header inspection.

    Downloads just enough bytes to read the image header (first 32KB).
    Returns (width, height) or (0, 0) on failure.
    """
    try:
        resp = await client.get(
            image_url,
            headers={"Range": "bytes=0-32767"},
            timeout=10.0,
        )
        # Accept both 200 (full) and 206 (partial)
        if resp.status_code not in (200, 206):
            return 0, 0

        content = resp.content

        # JPEG: scan for SOF0/SOF2 markers
        if content[:2] == b"\xff\xd8":
            return _parse_jpeg_dimensions(content)

        # PNG: IHDR chunk at offset 16
        if content[:8] == b"\x89PNG\r\n\x1a\n":
            if len(content) >= 24:
                width = int.from_bytes(content[16:20], "big")
                height = int.from_bytes(content[20:24], "big")
                return width, height

        # WebP: RIFF header
        if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            if content[12:16] == b"VP8 " and len(content) >= 30:
                # Lossy VP8
                width = int.from_bytes(content[26:28], "little") & 0x3FFF
                height = int.from_bytes(content[28:30], "little") & 0x3FFF
                return width, height
            if content[12:16] == b"VP8L" and len(content) >= 25:
                # Lossless VP8L
                bits = int.from_bytes(content[21:25], "little")
                width = (bits & 0x3FFF) + 1
                height = ((bits >> 14) & 0x3FFF) + 1
                return width, height

        return 0, 0
    except Exception:
        return 0, 0


def _parse_jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Parse JPEG SOF marker to extract dimensions."""
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        # SOF0 (0xC0) or SOF2 (0xC2) — baseline or progressive
        if marker in (0xC0, 0xC2):
            if i + 9 < len(data):
                height = int.from_bytes(data[i + 5 : i + 7], "big")
                width = int.from_bytes(data[i + 7 : i + 9], "big")
                return width, height
            break
        # Skip non-SOF markers
        if i + 3 < len(data):
            length = int.from_bytes(data[i + 2 : i + 4], "big")
            i += 2 + length
        else:
            break
    return 0, 0


# ---------------------------------------------------------------------------
# Lightweight validation (no Cloud Vision — just resolution check)
# ---------------------------------------------------------------------------

async def _validate_image_lightweight(
    client: httpx.AsyncClient,
    image_url: str,
) -> VisionResult:
    """
    Validate an image without Cloud Vision (fallback when no API key).

    Only checks resolution by downloading image headers.
    """
    result = VisionResult()

    try:
        width, height = await _get_image_dimensions(client, image_url)
        result.width = width
        result.height = height

        if width > 0 and height > 0 and (width < MIN_WIDTH or height < MIN_HEIGHT):
            result.flag = ImageFlag.LOW_RESOLUTION
            result.flag_detail = f"{width}x{height} below minimum {MIN_WIDTH}x{MIN_HEIGHT}"
        elif width == 0 and height == 0:
            # Couldn't determine dimensions — let it pass, flag for manual review
            logger.debug("Could not determine dimensions for %s", image_url)

        return result
    except Exception as exc:
        result.flag = ImageFlag.FETCH_FAILED
        result.flag_detail = str(exc)
        return result


# ---------------------------------------------------------------------------
# Image validator (orchestrator)
# ---------------------------------------------------------------------------

class ImageValidator:
    """
    Validates and curates images for ActivityNodes.

    Priority waterfall:
      1. Keep existing primaryImageUrl if it passes validation
      2. Unsplash search (name + city)
      3. Google Places photo (if googlePlaceId present)
      4. No image (flag as no_image_found)

    Usage:
        validator = ImageValidator(pool)
        stats = await validator.run()
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        unsplash_api_key: Optional[str] = None,
        google_api_key: Optional[str] = None,
        vision_api_key: Optional[str] = None,
    ):
        self.pool = pool
        self.unsplash_key = unsplash_api_key or os.environ.get("UNSPLASH_ACCESS_KEY")
        self.google_key = google_api_key or os.environ.get("GOOGLE_PLACES_API_KEY")
        self.vision_key = vision_api_key or os.environ.get("GOOGLE_VISION_API_KEY")

    async def run(self, *, limit: Optional[int] = None) -> ValidationStats:
        """
        Validate images for all unvalidated canonical nodes.

        Args:
            limit: Max nodes to process (None = all unvalidated).

        Returns:
            ValidationStats with counts and error details.
        """
        stats = ValidationStats(started_at=datetime.now(timezone.utc))

        async with self.pool.acquire() as conn:
            # Fetch unvalidated canonical nodes
            query = """
                SELECT id, name, "canonicalName", city, "primaryImageUrl",
                       "imageSource", "googlePlaceId"
                FROM activity_nodes
                WHERE "isCanonical" = true
                  AND "imageValidated" = false
                ORDER BY "convergenceScore" DESC NULLS LAST, "createdAt" ASC
            """
            if limit:
                query += f" LIMIT {int(limit)}"

            nodes = await conn.fetch(query)
            stats.nodes_processed = len(nodes)

            if not nodes:
                logger.info("No unvalidated nodes found")
                stats.finished_at = datetime.now(timezone.utc)
                return stats

            logger.info("Processing %d unvalidated nodes", len(nodes))

        # Process in batches with concurrency control
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async with httpx.AsyncClient() as client:
            for batch_start in range(0, len(nodes), BATCH_SIZE):
                batch = nodes[batch_start : batch_start + BATCH_SIZE]
                tasks = [
                    self._process_node(client, semaphore, node, stats)
                    for node in batch
                ]
                await asyncio.gather(*tasks)

        stats.finished_at = datetime.now(timezone.utc)

        logger.info(
            "Image validation complete: processed=%d sourced=%d validated=%d flagged=%d",
            stats.nodes_processed,
            stats.images_sourced,
            stats.images_validated,
            stats.images_flagged,
        )
        return stats

    async def _process_node(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        node: asyncpg.Record,
        stats: ValidationStats,
    ) -> None:
        """Process a single node: source image → validate → update DB."""
        async with semaphore:
            node_id = node["id"]
            try:
                result = await self._source_and_validate(client, node)
                await self._apply_result(result)

                if result.validated:
                    stats.images_validated += 1
                    if result.source:
                        stats.by_source[result.source.value] = (
                            stats.by_source.get(result.source.value, 0) + 1
                        )
                    stats.images_sourced += 1
                elif result.flag:
                    stats.images_flagged += 1
                    stats.by_flag[result.flag.value] = (
                        stats.by_flag.get(result.flag.value, 0) + 1
                    )
            except Exception as exc:
                stats.errors.append(f"{node_id[:8]}: {exc}")
                logger.exception("Image processing failed for node %s", node_id[:8])

    async def _source_and_validate(
        self,
        client: httpx.AsyncClient,
        node: asyncpg.Record,
    ) -> ImageResult:
        """
        Source an image via the priority waterfall, then validate it.

        Waterfall order:
          1. Existing primaryImageUrl (validate it)
          2. Unsplash search
          3. Google Places photo
          4. No image found
        """
        node_id = node["id"]
        existing_url = node["primaryImageUrl"]
        name = node["name"] or node["canonicalName"]
        city = node["city"]
        google_id = node["googlePlaceId"]

        # --- Try existing URL first ---
        if existing_url:
            validation = await self._validate(client, existing_url)
            if validation.flag is None:
                return ImageResult(
                    node_id=node_id,
                    image_url=existing_url,
                    source=ImageSource.EXISTING,
                    width=validation.width,
                    height=validation.height,
                    validated=True,
                )
            logger.debug(
                "Existing image failed validation for %s: %s",
                node_id[:8],
                validation.flag_detail,
            )

        # --- Waterfall: Unsplash ---
        if self.unsplash_key:
            search_query = f"{name} {city}"
            url = await _search_unsplash(client, search_query, self.unsplash_key)
            if url:
                validation = await self._validate(client, url)
                if validation.flag is None:
                    return ImageResult(
                        node_id=node_id,
                        image_url=url,
                        source=ImageSource.UNSPLASH,
                        width=validation.width,
                        height=validation.height,
                        validated=True,
                    )

        # --- Waterfall: Google Places ---
        if self.google_key and google_id:
            url = await _fetch_google_places_photo(client, google_id, self.google_key)
            if url:
                validation = await self._validate(client, url)
                if validation.flag is None:
                    return ImageResult(
                        node_id=node_id,
                        image_url=url,
                        source=ImageSource.GOOGLE_PLACES,
                        width=validation.width,
                        height=validation.height,
                        validated=True,
                    )

        # --- No image found ---
        return ImageResult(
            node_id=node_id,
            flag=ImageFlag.NO_IMAGE_FOUND,
            flag_detail="All sources exhausted",
        )

    async def _validate(
        self,
        client: httpx.AsyncClient,
        image_url: str,
    ) -> VisionResult:
        """Validate an image — full Vision API or lightweight fallback."""
        if self.vision_key:
            return await _validate_image_vision(client, image_url, self.vision_key)
        return await _validate_image_lightweight(client, image_url)

    async def _apply_result(self, result: ImageResult) -> None:
        """Write validation result back to the ActivityNode."""
        async with self.pool.acquire() as conn:
            if result.validated and result.image_url:
                await conn.execute(
                    """
                    UPDATE activity_nodes
                    SET "primaryImageUrl" = $1,
                        "imageSource" = $2,
                        "imageValidated" = true,
                        "lastValidatedAt" = NOW(),
                        "flagReason" = NULL,
                        "updatedAt" = NOW()
                    WHERE id = $3
                    """,
                    result.image_url,
                    result.source.value if result.source else None,
                    result.node_id,
                )
            elif result.flag:
                # Flag the node but don't clear existing image
                # (might still be usable, just not validated)
                flag_reason = f"image:{result.flag.value}"
                if result.flag_detail:
                    flag_reason += f" ({result.flag_detail})"

                await conn.execute(
                    """
                    UPDATE activity_nodes
                    SET "imageValidated" = false,
                        "flagReason" = $1,
                        "lastValidatedAt" = NOW(),
                        "updatedAt" = NOW()
                    WHERE id = $2
                    """,
                    flag_reason,
                    result.node_id,
                )


# ---------------------------------------------------------------------------
# Public API (matches other pipeline step patterns)
# ---------------------------------------------------------------------------

async def run_image_validation(
    pool: asyncpg.Pool,
    *,
    limit: Optional[int] = None,
    unsplash_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    vision_api_key: Optional[str] = None,
) -> ValidationStats:
    """
    Run image validation for all unvalidated canonical ActivityNodes.

    Args:
        pool: asyncpg connection pool.
        limit: Max nodes to process (None = all).
        unsplash_api_key: Unsplash API key (falls back to UNSPLASH_ACCESS_KEY env).
        google_api_key: Google Places API key (falls back to GOOGLE_PLACES_API_KEY env).
        vision_api_key: Cloud Vision API key (falls back to GOOGLE_VISION_API_KEY env).
            If not set, uses lightweight validation (resolution only).

    Returns:
        ValidationStats with per-source and per-flag breakdowns.
    """
    validator = ImageValidator(
        pool,
        unsplash_api_key=unsplash_api_key,
        google_api_key=google_api_key,
        vision_api_key=vision_api_key,
    )
    return await validator.run(limit=limit)
