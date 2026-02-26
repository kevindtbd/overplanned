"""Source bundle assembler for Pipeline D LLM Research Synthesis."""
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable

from services.api.pipeline.gcs_raw_store import read_research_bundle

logger = logging.getLogger(__name__)

TOKEN_BUDGET = 40_000
TRIM_TARGET = 35_000
CHARS_PER_TOKEN = 4

MIN_UPVOTE_RATIO = 0.70
MIN_SCORE = 10
MAX_TOP_THREADS = 15
MAX_BLOG_EXCERPTS = 10
BLOG_TRIM_CHARS = 800
EDITORIAL_TRIM_CHARS = 600
AMPLIFICATION_THRESHOLD = 0.40

ContentReader = Callable[[str, str], Awaitable[list[dict]]]


@dataclass
class SourceBundle:
    city_slug: str
    reddit_top: list[dict] = field(default_factory=list)
    reddit_local: list[dict] = field(default_factory=list)
    blog_excerpts: list[dict] = field(default_factory=list)
    atlas_entries: list[dict] = field(default_factory=list)
    editorial: list[dict] = field(default_factory=list)
    places_metadata: list[dict] = field(default_factory=list)
    amplification_suspects: list[str] = field(default_factory=list)
    token_estimate: int = 0

    @property
    def all_snippets(self) -> list[dict]:
        return (self.reddit_top + self.reddit_local + self.blog_excerpts
                + self.atlas_entries + self.editorial)


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _estimate_bundle_tokens(bundle: SourceBundle) -> int:
    total = 0
    for source_list in [bundle.reddit_top, bundle.reddit_local, bundle.blog_excerpts,
                        bundle.atlas_entries, bundle.editorial, bundle.places_metadata]:
        for rec in source_list:
            total += _estimate_tokens(str(rec.get("body", "")) + str(rec.get("title", "")))
    return total


async def assemble_source_bundle(
    city_slug: str,
    *,
    content_reader: Optional[ContentReader] = None,
) -> SourceBundle:
    """Assemble grounding material from GCS research bundles."""
    reader = content_reader or read_research_bundle
    bundle = SourceBundle(city_slug=city_slug)

    reddit_raw = await reader(city_slug, "reddit")
    blogs_raw = await reader(city_slug, "blogs")
    atlas_raw = await reader(city_slug, "atlas")
    editorial_raw = await reader(city_slug, "editorial")
    places_raw = await reader(city_slug, "places_metadata")

    bundle.reddit_local = [r for r in reddit_raw if r.get("is_local")]
    quality = [r for r in reddit_raw
               if not r.get("is_local")
               and r.get("upvote_ratio", 0) >= MIN_UPVOTE_RATIO
               and r.get("score", 0) >= MIN_SCORE]
    quality.sort(key=lambda r: r.get("upvote_ratio", 0) * r.get("score", 0), reverse=True)
    bundle.reddit_top = quality[:MAX_TOP_THREADS]

    for b in blogs_raw[:MAX_BLOG_EXCERPTS]:
        trimmed = dict(b)
        if trimmed.get("body") and len(trimmed["body"]) > BLOG_TRIM_CHARS:
            trimmed["body"] = trimmed["body"][:BLOG_TRIM_CHARS]
        bundle.blog_excerpts.append(trimmed)

    bundle.atlas_entries = atlas_raw

    for e in editorial_raw:
        trimmed = dict(e)
        if trimmed.get("body") and len(trimmed["body"]) > EDITORIAL_TRIM_CHARS:
            trimmed["body"] = trimmed["body"][:EDITORIAL_TRIM_CHARS]
        bundle.editorial.append(trimmed)

    bundle.places_metadata = places_raw
    bundle.amplification_suspects = check_amplification(bundle.all_snippets, threshold=AMPLIFICATION_THRESHOLD)

    bundle.token_estimate = _estimate_bundle_tokens(bundle)
    while bundle.token_estimate > TRIM_TARGET and bundle.reddit_top:
        bundle.reddit_top.pop()
        bundle.token_estimate = _estimate_bundle_tokens(bundle)

    return bundle


def filter_snippets_for_venues(
    snippets: list[dict],
    venue_names: list[str],
) -> list[dict]:
    """Filter source snippets to those mentioning any of the given venue names."""
    if not venue_names:
        return []
    patterns = [re.compile(re.escape(name), re.IGNORECASE) for name in venue_names]
    result = []
    for snippet in snippets:
        text = str(snippet.get("body", "")) + " " + str(snippet.get("title", ""))
        if any(p.search(text) for p in patterns):
            result.append(snippet)
    return result


def check_amplification(
    snippets: list[dict],
    threshold: float = AMPLIFICATION_THRESHOLD,
) -> list[str]:
    """Detect venue names appearing in >threshold fraction of documents."""
    if not snippets:
        return []
    name_pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
    name_counts: dict[str, int] = {}
    for snippet in snippets:
        text = str(snippet.get("body", "")) + " " + str(snippet.get("title", ""))
        found_in_doc: set[str] = set()
        for match in name_pattern.finditer(text):
            found_in_doc.add(match.group(1).lower())
        for name in found_in_doc:
            name_counts[name] = name_counts.get(name, 0) + 1

    total = len(snippets)
    return [name for name, count in name_counts.items() if count / total > threshold]
