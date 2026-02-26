"""
Entity resolution for ActivityNodes — the "7-Eleven problem."

Resolves multiple references to the same real-world venue into a single
canonical ActivityNode through a 4-tier matching cascade:
  1. External ID match (foursquareId / googlePlaceId)
  2. Geocode proximity (PostGIS ST_DWithin < 50m) + same category
  3. Fuzzy name (pg_trgm similarity > 0.7 on canonicalName)
  4. Content hash (SHA-256 of normalized name + lat + lng + category)

Merge protocol:
  - Losing node: resolvedToId → winner, isCanonical = false
  - ActivityAlias created from losing node's name
  - QualitySignals + ActivityNodeVibeTags migrated to winner
"""

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

import asyncpg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

# Common suffixes stripped during normalization (case-insensitive).
# Order matters: longest first to avoid partial matches.
STRIP_SUFFIXES = [
    # English
    "restaurant", "coffee shop", "coffee house",
    "cafe", "bar", "pub", "tavern", "izakaya",
    "bistro", "brasserie",
    "hotel", "hostel", "inn", "motel",
    "museum", "gallery", "theater", "theatre",
    "park", "garden", "gardens",
    "spa", "salon",
    "shop", "store", "boutique", "market",
    "temple", "shrine", "church", "mosque",
    "station", "terminal",
    # Italian
    "ristorante", "trattoria",
    # Spanish (with and without accents -- NFKC handles some,
    # but we list both forms for safety)
    "restaurante",
    "taqueria", "taquería",
    "cantina",
    "mercado",
    "panaderia", "panadería",
    "cerveceria", "cervecería",
    "pulqueria", "pulquería",
    "mezcaleria", "mezcalería",
    "fonda",
    "comedor",
    "loncheria", "lonchería",
    "cocina",
    "antojitos",
    # Spanish prefixes handled as suffixes (they appear at word boundaries)
    "el", "la", "los", "las",
    # French (common in New Orleans)
    "boulangerie", "patisserie", "pâtisserie",
    "boucherie",
    # Accented cafe/café (both forms)
    "café",
]

# Katakana ↔ Hiragana offset (Unicode block distance)
_KATA_HIRA_OFFSET = ord("ぁ") - ord("ァ")


def _katakana_to_hiragana(text: str) -> str:
    """Convert katakana characters to hiragana for equivalence matching."""
    result = []
    for ch in text:
        cp = ord(ch)
        # Katakana range: U+30A1..U+30F6
        if 0x30A1 <= cp <= 0x30F6:
            result.append(chr(cp + _KATA_HIRA_OFFSET))
        else:
            result.append(ch)
    return "".join(result)


_PUNCT_RE = re.compile(r"['\"\-.,!?&()]+")


def _normalize_for_containment(name: str) -> str:
    """
    Normalize a venue name for substring containment matching.

    Strips punctuation (apostrophes, hyphens, etc.), lowercases,
    and collapses whitespace. "Salamone's" -> "salamones",
    "E9 Firehouse & Gastropub" -> "e9 firehouse gastropub".
    """
    return _PUNCT_RE.sub("", name).lower().strip()


def strip_accents(text: str) -> str:
    """
    Remove diacritical marks (accents) from text.

    e with accent -> e, n with tilde -> n, etc.
    Uses NFD decomposition to split base characters from combining marks,
    then strips the combining marks.

    This is applied AFTER NFKC normalization and is specifically for
    cross-language matching (e.g. "taqueria" == "taquería").
    """
    # NFD decomposes accented chars into base + combining mark
    nfd = unicodedata.normalize("NFD", text)
    # Filter out combining marks (category "M")
    return "".join(ch for ch in nfd if unicodedata.category(ch)[0] != "M")


def normalize_name(raw_name: str) -> str:
    """
    Normalize a venue name for comparison.

    Steps:
      1. Unicode NFKC normalization (collapses fullwidth, compatibility chars)
      2. Katakana -> Hiragana equivalence
      3. Lowercase
      4. Strip diacritical marks (accents) for cross-language matching
      5. Strip punctuation (keep CJK, letters, digits, spaces)
      6. Strip common suffixes
      7. Collapse whitespace
    """
    if not raw_name:
        return ""

    # NFKC normalization -- handles CJK fullwidth, compatibility forms
    text = unicodedata.normalize("NFKC", raw_name)

    # Katakana -> Hiragana
    text = _katakana_to_hiragana(text)

    # Lowercase
    text = text.lower()

    # Strip accents/diacriticals (cafe == cafe, taqueria == taqueria)
    text = strip_accents(text)

    # Strip punctuation but keep CJK ideographs, letters, digits, spaces
    # CJK Unified Ideographs: U+4E00..U+9FFF
    # Hiragana: U+3040..U+309F
    # Katakana: U+30A0..U+30FF (already converted, but keep range for safety)
    # CJK Extension A: U+3400..U+4DBF
    text = re.sub(
        r"[^\w\s\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\u3400-\u4dbf]",
        " ",
        text,
    )

    # Strip common suffixes (word-boundary match)
    for suffix in STRIP_SUFFIXES:
        # Also strip the accent-stripped version of the suffix
        stripped_suffix = strip_accents(suffix)
        text = re.sub(rf"\b{re.escape(stripped_suffix)}\b", "", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def compute_content_hash(name: str, lat: float, lng: float, category: str) -> str:
    """
    SHA-256 hash of normalized (name + lat + lng + category).

    Lat/lng rounded to 4 decimal places (~11m precision) to catch
    minor geocoding drift across sources.
    """
    normalized = normalize_name(name)
    payload = f"{normalized}|{lat:.4f}|{lng:.4f}|{category}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Resolution data structures
# ---------------------------------------------------------------------------

class MatchTier(str, Enum):
    """How two nodes were matched."""
    EXTERNAL_ID = "external_id"
    GEOCODE = "geocode_proximity"
    FUZZY_NAME = "fuzzy_name"
    CONTENT_HASH = "content_hash"


@dataclass
class MergeCandidate:
    """A pair of nodes identified as potential duplicates."""
    winner_id: str
    loser_id: str
    tier: MatchTier
    confidence: float  # 0.0–1.0
    detail: str = ""


@dataclass
class MergeResult:
    """Outcome of a single merge operation."""
    winner_id: str
    loser_id: str
    tier: MatchTier
    aliases_created: int = 0
    signals_migrated: int = 0
    vibe_tags_migrated: int = 0


@dataclass
class ResolutionStats:
    """Aggregate stats from a resolution run."""
    nodes_scanned: int = 0
    candidates_found: int = 0
    merges_executed: int = 0
    merges_by_tier: dict = field(default_factory=lambda: {
        MatchTier.EXTERNAL_ID: 0,
        MatchTier.GEOCODE: 0,
        MatchTier.FUZZY_NAME: 0,
        MatchTier.CONTENT_HASH: 0,
    })
    errors: int = 0
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Entity Resolver
# ---------------------------------------------------------------------------

class EntityResolver:
    """
    Resolves duplicate ActivityNodes into canonical entries.

    Usage:
        resolver = EntityResolver(pool)
        stats = await resolver.resolve_incremental()   # after each scrape
        stats = await resolver.resolve_full_sweep()     # weekly cron
    """

    # Geocode proximity threshold in meters
    PROXIMITY_METERS = 50

    # pg_trgm similarity threshold
    FUZZY_THRESHOLD = 0.7

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve_incremental(self, since: Optional[datetime] = None) -> ResolutionStats:
        """
        Resolve new nodes only (fast, run after each scrape).

        Args:
            since: Only consider nodes created after this timestamp.
                   Defaults to 24 hours ago if not specified.
        """
        stats = ResolutionStats(started_at=datetime.now(timezone.utc))

        if since is None:
            since = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0,
            ).replace(tzinfo=None)

        async with self.pool.acquire() as conn:
            # Get new canonical nodes
            new_nodes = await conn.fetch(
                """
                SELECT id, "canonicalName", "foursquareId", "googlePlaceId",
                       latitude, longitude, category, "contentHash", name, city
                FROM activity_nodes
                WHERE "isCanonical" = true
                  AND "createdAt" >= $1
                ORDER BY "createdAt" ASC
                """,
                since,
            )
            stats.nodes_scanned = len(new_nodes)

            for node in new_nodes:
                candidates = await self._find_candidates(conn, node)
                stats.candidates_found += len(candidates)

                for candidate in candidates:
                    try:
                        result = await self._execute_merge(conn, candidate)
                        stats.merges_executed += 1
                        stats.merges_by_tier[candidate.tier] += 1
                        logger.info(
                            "Merged %s → %s via %s",
                            result.loser_id[:8],
                            result.winner_id[:8],
                            candidate.tier.value,
                        )
                    except Exception:
                        stats.errors += 1
                        logger.exception(
                            "Merge failed: %s → %s",
                            candidate.loser_id[:8],
                            candidate.winner_id[:8],
                        )

        stats.finished_at = datetime.now(timezone.utc)
        return stats

    async def resolve_full_sweep(self) -> ResolutionStats:
        """
        Resolve all canonical nodes (slow, run weekly).

        Scans every canonical node against every other canonical node.
        Catches retroactive duplicates from cross-source convergence.
        """
        stats = ResolutionStats(started_at=datetime.now(timezone.utc))

        async with self.pool.acquire() as conn:
            # Backfill content hashes for any nodes missing them
            await self._backfill_content_hashes(conn)

            # Phase 1: Content hash exact matches (cheapest, batch-able)
            hash_merges = await self._find_content_hash_dupes(conn)
            stats.candidates_found += len(hash_merges)
            for candidate in hash_merges:
                try:
                    await self._execute_merge(conn, candidate)
                    stats.merges_executed += 1
                    stats.merges_by_tier[MatchTier.CONTENT_HASH] += 1
                except Exception:
                    stats.errors += 1
                    logger.exception("Hash merge failed")

            # Phase 2: External ID matches
            ext_merges = await self._find_external_id_dupes(conn)
            stats.candidates_found += len(ext_merges)
            for candidate in ext_merges:
                try:
                    await self._execute_merge(conn, candidate)
                    stats.merges_executed += 1
                    stats.merges_by_tier[MatchTier.EXTERNAL_ID] += 1
                except Exception:
                    stats.errors += 1
                    logger.exception("External ID merge failed")

            # Phase 3: Geocode + fuzzy name (most expensive)
            all_canonical = await conn.fetch(
                """
                SELECT id, "canonicalName", "foursquareId", "googlePlaceId",
                       latitude, longitude, category, "contentHash", name, city
                FROM activity_nodes
                WHERE "isCanonical" = true
                ORDER BY "createdAt" ASC
                """,
            )
            stats.nodes_scanned = len(all_canonical)

            for node in all_canonical:
                # Skip if already merged in this run
                is_still_canonical = await conn.fetchval(
                    'SELECT "isCanonical" FROM activity_nodes WHERE id = $1',
                    node["id"],
                )
                if not is_still_canonical:
                    continue

                candidates = await self._find_geo_fuzzy_candidates(conn, node)
                stats.candidates_found += len(candidates)
                for candidate in candidates:
                    try:
                        await self._execute_merge(conn, candidate)
                        stats.merges_executed += 1
                        stats.merges_by_tier[candidate.tier] += 1
                    except Exception:
                        stats.errors += 1
                        logger.exception("Geo/fuzzy merge failed")

        stats.finished_at = datetime.now(timezone.utc)
        return stats

    # ------------------------------------------------------------------
    # Candidate finding
    # ------------------------------------------------------------------

    async def _find_candidates(
        self, conn: asyncpg.Connection, node: asyncpg.Record
    ) -> list[MergeCandidate]:
        """
        Find merge candidates for a single node using the 4-tier cascade.

        Stops at the first tier that finds a match (higher tiers are
        more confident, so no need to check lower tiers).
        """
        node_id = node["id"]

        # Tier 1: External ID match
        candidates = await self._match_external_id(conn, node)
        if candidates:
            return candidates

        # Tier 2: Geocode proximity + same category
        candidates = await self._match_geocode(conn, node)
        if candidates:
            return candidates

        # Tier 3: Fuzzy name match
        candidates = await self._match_fuzzy_name(conn, node)
        if candidates:
            return candidates

        # Tier 4: Content hash match
        candidates = await self._match_content_hash(conn, node)
        if candidates:
            return candidates

        return []

    async def _match_external_id(
        self, conn: asyncpg.Connection, node: asyncpg.Record
    ) -> list[MergeCandidate]:
        """Tier 1: Exact match on foursquareId or googlePlaceId."""
        candidates = []

        for id_field in ("foursquareId", "googlePlaceId"):
            ext_id = node[id_field]
            if not ext_id:
                continue

            match = await conn.fetchrow(
                f"""
                SELECT id FROM activity_nodes
                WHERE "{id_field}" = $1
                  AND id != $2
                  AND "isCanonical" = true
                """,
                ext_id,
                node["id"],
            )
            if match:
                winner_id, loser_id = self._pick_winner(
                    conn, match["id"], node["id"]
                )
                candidates.append(MergeCandidate(
                    winner_id=winner_id,
                    loser_id=loser_id,
                    tier=MatchTier.EXTERNAL_ID,
                    confidence=1.0,
                    detail=f"{id_field}={ext_id}",
                ))

        return candidates

    async def _match_geocode(
        self, conn: asyncpg.Connection, node: asyncpg.Record
    ) -> list[MergeCandidate]:
        """
        Tier 2: PostGIS ST_DWithin proximity + same ActivityCategory.

        Uses geography type for accurate meter-based distance.
        Excludes exact-coordinate matches (distance < 1m) — those are
        fallback city-center coordinates from LLM extraction, not real
        geocoded positions.
        """
        matches = await conn.fetch(
            """
            SELECT id, "canonicalName"
            FROM activity_nodes
            WHERE id != $1
              AND "isCanonical" = true
              AND category = $2
              AND ST_DWithin(
                  ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                  ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography,
                  $5
              )
              AND ST_Distance(
                  ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                  ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography
              ) > 1.0
            """,
            node["id"],
            node["category"],
            node["longitude"],
            node["latitude"],
            self.PROXIMITY_METERS,
        )

        candidates = []
        for match in matches:
            winner_id, loser_id = self._pick_winner(
                conn, match["id"], node["id"]
            )
            candidates.append(MergeCandidate(
                winner_id=winner_id,
                loser_id=loser_id,
                tier=MatchTier.GEOCODE,
                confidence=0.85,
                detail=f"within {self.PROXIMITY_METERS}m, same category={node['category']}",
            ))

        return candidates

    async def _match_fuzzy_name(
        self, conn: asyncpg.Connection, node: asyncpg.Record
    ) -> list[MergeCandidate]:
        """
        Tier 3: pg_trgm trigram similarity on canonicalName.

        Two sub-checks:
        1. Standard trigram similarity > FUZZY_THRESHOLD (0.7)
        2. Normalized containment: if the shorter name (stripped of
           punctuation) is fully contained in the longer one and both
           are same category, match with confidence 0.80. Catches
           "El Toro" vs "El Toro on Pearl", "7 Seas" vs "7 Seas
           Brewery and Taproom", "Salamones" vs "Salamone's".

        Requires pg_trgm extension (CREATE EXTENSION IF NOT EXISTS pg_trgm).
        """
        # Sub-check 1: standard trigram similarity
        matches = await conn.fetch(
            """
            SELECT id, "canonicalName",
                   similarity("canonicalName", $2) AS sim
            FROM activity_nodes
            WHERE id != $1
              AND "isCanonical" = true
              AND category = $3
              AND similarity("canonicalName", $2) > $4
            ORDER BY sim DESC
            LIMIT 5
            """,
            node["id"],
            node["canonicalName"],
            node["category"],
            self.FUZZY_THRESHOLD,
        )

        candidates = []
        seen_ids = set()
        for match in matches:
            seen_ids.add(match["id"])
            winner_id, loser_id = self._pick_winner(
                conn, match["id"], node["id"]
            )
            candidates.append(MergeCandidate(
                winner_id=winner_id,
                loser_id=loser_id,
                tier=MatchTier.FUZZY_NAME,
                confidence=float(match["sim"]),
                detail=f'"{node["canonicalName"]}" ~ "{match["canonicalName"]}" (sim={match["sim"]:.3f})',
            ))

        # Sub-check 2: normalized containment
        # Strip punctuation for comparison, check if shorter is in longer
        node_name = node["canonicalName"]
        node_norm = _normalize_for_containment(node_name)
        if len(node_norm) >= 3:  # skip trivially short names
            containment_matches = await conn.fetch(
                """
                SELECT id, "canonicalName"
                FROM activity_nodes
                WHERE id != $1
                  AND "isCanonical" = true
                  AND category = $2
                  AND city = $3
                LIMIT 200
                """,
                node["id"],
                node["category"],
                node.get("city", ""),
            )
            for match in containment_matches:
                if match["id"] in seen_ids:
                    continue
                match_norm = _normalize_for_containment(match["canonicalName"])
                shorter, longer = sorted([node_norm, match_norm], key=len)
                if len(shorter) >= 3 and shorter in longer:
                    seen_ids.add(match["id"])
                    winner_id, loser_id = self._pick_winner(
                        conn, match["id"], node["id"]
                    )
                    candidates.append(MergeCandidate(
                        winner_id=winner_id,
                        loser_id=loser_id,
                        tier=MatchTier.FUZZY_NAME,
                        confidence=0.80,
                        detail=f'containment: "{shorter}" in "{longer}"',
                    ))

        return candidates

    async def _match_content_hash(
        self, conn: asyncpg.Connection, node: asyncpg.Record
    ) -> list[MergeCandidate]:
        """Tier 4: Exact match on content hash."""
        content_hash = node["contentHash"]
        if not content_hash:
            # Compute on the fly if missing
            content_hash = compute_content_hash(
                node["canonicalName"],
                node["latitude"],
                node["longitude"],
                node["category"],
            )

        match = await conn.fetchrow(
            """
            SELECT id FROM activity_nodes
            WHERE "contentHash" = $1
              AND id != $2
              AND "isCanonical" = true
            """,
            content_hash,
            node["id"],
        )

        if not match:
            return []

        winner_id, loser_id = self._pick_winner(
            conn, match["id"], node["id"]
        )
        return [MergeCandidate(
            winner_id=winner_id,
            loser_id=loser_id,
            tier=MatchTier.CONTENT_HASH,
            confidence=0.95,
            detail=f"hash={content_hash[:16]}...",
        )]

    # ------------------------------------------------------------------
    # Batch finders (full sweep)
    # ------------------------------------------------------------------

    async def _find_content_hash_dupes(
        self, conn: asyncpg.Connection
    ) -> list[MergeCandidate]:
        """Find all canonical nodes sharing the same content hash."""
        dupes = await conn.fetch(
            """
            SELECT "contentHash", array_agg(id ORDER BY "createdAt" ASC) AS ids
            FROM activity_nodes
            WHERE "isCanonical" = true
              AND "contentHash" IS NOT NULL
            GROUP BY "contentHash"
            HAVING count(*) > 1
            """,
        )

        candidates = []
        for row in dupes:
            ids = row["ids"]
            winner_id = ids[0]  # oldest = canonical winner
            for loser_id in ids[1:]:
                candidates.append(MergeCandidate(
                    winner_id=winner_id,
                    loser_id=loser_id,
                    tier=MatchTier.CONTENT_HASH,
                    confidence=0.95,
                    detail=f"hash={row['contentHash'][:16]}...",
                ))

        return candidates

    async def _find_external_id_dupes(
        self, conn: asyncpg.Connection
    ) -> list[MergeCandidate]:
        """Find canonical nodes sharing foursquareId or googlePlaceId."""
        candidates = []

        for id_field in ("foursquareId", "googlePlaceId"):
            dupes = await conn.fetch(
                f"""
                SELECT "{id_field}", array_agg(id ORDER BY "createdAt" ASC) AS ids
                FROM activity_nodes
                WHERE "isCanonical" = true
                  AND "{id_field}" IS NOT NULL
                GROUP BY "{id_field}"
                HAVING count(*) > 1
                """,
            )

            for row in dupes:
                ids = row["ids"]
                winner_id = ids[0]
                for loser_id in ids[1:]:
                    candidates.append(MergeCandidate(
                        winner_id=winner_id,
                        loser_id=loser_id,
                        tier=MatchTier.EXTERNAL_ID,
                        confidence=1.0,
                        detail=f"{id_field}={row[id_field]}",
                    ))

        return candidates

    async def _find_geo_fuzzy_candidates(
        self, conn: asyncpg.Connection, node: asyncpg.Record
    ) -> list[MergeCandidate]:
        """
        Combined geo-proximity + fuzzy name check for full sweep.

        Finds nodes within PROXIMITY_METERS with same category,
        then applies fuzzy name filter. Excludes exact-coordinate
        matches (< 1m) which indicate fallback city-center coords.
        """
        matches = await conn.fetch(
            """
            SELECT id, "canonicalName",
                   similarity("canonicalName", $2) AS sim
            FROM activity_nodes
            WHERE id != $1
              AND "isCanonical" = true
              AND category = $3
              AND ST_DWithin(
                  ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                  ST_SetSRID(ST_MakePoint($4, $5), 4326)::geography,
                  $6
              )
              AND ST_Distance(
                  ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography,
                  ST_SetSRID(ST_MakePoint($4, $5), 4326)::geography
              ) > 1.0
              AND similarity("canonicalName", $2) > $7
            ORDER BY sim DESC
            """,
            node["id"],
            node["canonicalName"],
            node["category"],
            node["longitude"],
            node["latitude"],
            self.PROXIMITY_METERS,
            self.FUZZY_THRESHOLD,
        )

        candidates = []
        for match in matches:
            winner_id, loser_id = self._pick_winner(
                conn, match["id"], node["id"]
            )
            candidates.append(MergeCandidate(
                winner_id=winner_id,
                loser_id=loser_id,
                tier=MatchTier.GEOCODE,
                confidence=float(match["sim"]),
                detail=f'geo+fuzzy: "{node["canonicalName"]}" ~ "{match["canonicalName"]}"',
            ))

        return candidates

    # ------------------------------------------------------------------
    # Merge execution
    # ------------------------------------------------------------------

    async def _execute_merge(
        self, conn: asyncpg.Connection, candidate: MergeCandidate
    ) -> MergeResult:
        """
        Execute a merge within a single transaction.

        1. Mark loser: resolvedToId = winner, isCanonical = false
        2. Create ActivityAlias from loser's name
        3. Migrate QualitySignals
        4. Migrate ActivityNodeVibeTags (skip duplicates)
        5. Update winner's sourceCount
        """
        result = MergeResult(
            winner_id=candidate.winner_id,
            loser_id=candidate.loser_id,
            tier=candidate.tier,
        )

        async with conn.transaction():
            # Verify both nodes are still canonical (guard against race)
            check = await conn.fetch(
                """
                SELECT id, "isCanonical" FROM activity_nodes
                WHERE id = ANY($1)
                """,
                [candidate.winner_id, candidate.loser_id],
            )
            node_map = {r["id"]: r["isCanonical"] for r in check}

            if not node_map.get(candidate.winner_id, False):
                raise ValueError(f"Winner {candidate.winner_id[:8]} no longer canonical")
            if not node_map.get(candidate.loser_id, False):
                raise ValueError(f"Loser {candidate.loser_id[:8]} no longer canonical")

            # Get loser details for alias creation
            loser = await conn.fetchrow(
                """
                SELECT name, "canonicalName", "sourceCount",
                       "foursquareId", "googlePlaceId"
                FROM activity_nodes WHERE id = $1
                """,
                candidate.loser_id,
            )

            # 1. Mark loser as resolved
            await conn.execute(
                """
                UPDATE activity_nodes
                SET "resolvedToId" = $1,
                    "isCanonical" = false,
                    "updatedAt" = NOW()
                WHERE id = $2
                """,
                candidate.winner_id,
                candidate.loser_id,
            )

            # 2. Create ActivityAlias
            alias_name = loser["name"] or loser["canonicalName"]
            await conn.execute(
                """
                INSERT INTO activity_aliases (id, "activityNodeId", alias, source, "createdAt")
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT DO NOTHING
                """,
                str(uuid4()),
                candidate.winner_id,
                alias_name,
                f"entity_resolution:{candidate.tier.value}",
            )
            result.aliases_created = 1

            # 3. Migrate QualitySignals
            migrated_signals = await conn.execute(
                """
                UPDATE quality_signals
                SET "activityNodeId" = $1
                WHERE "activityNodeId" = $2
                """,
                candidate.winner_id,
                candidate.loser_id,
            )
            result.signals_migrated = _parse_command_tag_count(migrated_signals)

            # 4. Migrate ActivityNodeVibeTags (skip existing combos)
            migrated_tags = await conn.execute(
                """
                UPDATE activity_node_vibe_tags
                SET "activityNodeId" = $1
                WHERE "activityNodeId" = $2
                  AND ("vibeTagId", source) NOT IN (
                      SELECT "vibeTagId", source
                      FROM activity_node_vibe_tags
                      WHERE "activityNodeId" = $1
                  )
                """,
                candidate.winner_id,
                candidate.loser_id,
            )
            result.vibe_tags_migrated = _parse_command_tag_count(migrated_tags)

            # Delete any orphaned vibe tags left on loser (dupes that weren't migrated)
            await conn.execute(
                """
                DELETE FROM activity_node_vibe_tags
                WHERE "activityNodeId" = $1
                """,
                candidate.loser_id,
            )

            # 5. Copy external IDs to winner if winner is missing them
            for id_field in ("foursquareId", "googlePlaceId"):
                if loser[id_field]:
                    await conn.execute(
                        f"""
                        UPDATE activity_nodes
                        SET "{id_field}" = $1, "updatedAt" = NOW()
                        WHERE id = $2 AND "{id_field}" IS NULL
                        """,
                        loser[id_field],
                        candidate.winner_id,
                    )

            # 6. Update winner sourceCount
            await conn.execute(
                """
                UPDATE activity_nodes
                SET "sourceCount" = "sourceCount" + $1,
                    "updatedAt" = NOW()
                WHERE id = $2
                """,
                loser["sourceCount"] or 0,
                candidate.winner_id,
            )

        logger.info(
            "Merge complete: %s → %s | signals=%d tags=%d tier=%s",
            candidate.loser_id[:8],
            candidate.winner_id[:8],
            result.signals_migrated,
            result.vibe_tags_migrated,
            candidate.tier.value,
        )

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_winner(
        conn: asyncpg.Connection, existing_id: str, new_id: str
    ) -> tuple[str, str]:
        """
        Decide which node is the canonical winner.

        The existing (older) node wins — it has accumulated more signals
        and is likely referenced by more itinerary slots.

        Returns: (winner_id, loser_id)
        """
        # Existing node was found first → it's the winner
        return existing_id, new_id

    async def _backfill_content_hashes(self, conn: asyncpg.Connection) -> int:
        """Compute and store content hashes for nodes missing them."""
        nodes = await conn.fetch(
            """
            SELECT id, "canonicalName", latitude, longitude, category
            FROM activity_nodes
            WHERE "isCanonical" = true
              AND "contentHash" IS NULL
            """,
        )

        count = 0
        for node in nodes:
            content_hash = compute_content_hash(
                node["canonicalName"],
                node["latitude"],
                node["longitude"],
                node["category"],
            )
            await conn.execute(
                """
                UPDATE activity_nodes
                SET "contentHash" = $1, "updatedAt" = NOW()
                WHERE id = $2
                """,
                content_hash,
                node["id"],
            )
            count += 1

        if count:
            logger.info("Backfilled %d content hashes", count)
        return count


def _parse_command_tag_count(command_tag: str) -> int:
    """Extract row count from asyncpg command tag like 'UPDATE 5'."""
    try:
        return int(command_tag.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


# ---------------------------------------------------------------------------
# SQL setup helpers
# ---------------------------------------------------------------------------

REQUIRED_EXTENSIONS_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
"""

RECOMMENDED_INDEXES_SQL = """
-- Trigram index for fuzzy name matching
CREATE INDEX IF NOT EXISTS idx_activity_node_canonical_name_trgm
ON activity_nodes USING gin ("canonicalName" gin_trgm_ops);

-- Spatial index for geocode proximity queries
CREATE INDEX IF NOT EXISTS idx_activity_node_geography
ON activity_nodes USING gist (
    (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography)
);

-- Content hash lookup
CREATE INDEX IF NOT EXISTS idx_activity_node_content_hash
ON activity_nodes ("contentHash")
WHERE "isCanonical" = true;

-- Resolution lookup
CREATE INDEX IF NOT EXISTS idx_activity_node_resolved
ON activity_nodes ("resolvedToId")
WHERE "resolvedToId" IS NOT NULL;
"""


async def ensure_extensions(pool: asyncpg.Pool) -> None:
    """Ensure required Postgres extensions are installed."""
    async with pool.acquire() as conn:
        await conn.execute(REQUIRED_EXTENSIONS_SQL)


async def create_indexes(pool: asyncpg.Pool) -> None:
    """Create recommended indexes for entity resolution performance."""
    async with pool.acquire() as conn:
        await conn.execute(RECOMMENDED_INDEXES_SQL)
