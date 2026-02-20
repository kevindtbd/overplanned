# Reddit Data Access — Status & Alternatives
**Addendum to Bootstrap Intelligence Stack**  
*Updated February 2026*

---

## Current Status

Reddit's API registration is effectively locked for new applications as of 2023. The standard app registration flow (`reddit.com/prefs/apps`) now redirects to the Responsible Builder Policy and requires enterprise agreement for any meaningful data access. PRAW remains the right tool for when access is granted, but **free API access for new builders is not reliably available at launch**.

This does not block Overplanned. The bootstrap strategy can be executed fully without official Reddit API access.

---

## Access Alternatives (in priority order)

### 1. Arctic Shift (Primary — Free)
Community-maintained Reddit archive. Full historical dumps of posts and comments across all subreddits, updated regularly.

- **URL:** `arctic-shift.quantabase.com`
- **Access:** Free, no auth required for bulk downloads
- **Coverage:** Historical depth beyond 1000 posts/subreddit — better than PRAW's live limit
- **Format:** Parquet/JSONL dumps — drops directly into the scraping pipeline
- **Limitation:** Lag of days to weeks on very recent posts. Fine for bootstrap, not for real-time.

**Use for:** Pre-launch city seeding. Pull the full historical corpus for target subreddits, run LLM extraction batch once.

---

### 2. Direct HTTP Scraping (Secondary — Free)
Public Reddit pages are accessible without auth via `old.reddit.com` and the unofficial JSON endpoint.

```python
import requests
import time

def scrape_subreddit_json(subreddit, sort="top", limit=100):
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    headers = {"User-Agent": "Overplanned-Research/1.0"}
    params = {"limit": 100, "t": "all"}
    posts = []
    after = None

    while len(posts) < limit:
        if after:
            params["after"] = after
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()["data"]
        posts.extend(data["children"])
        after = data.get("after")
        if not after:
            break
        time.sleep(2)  # respect rate limits

    return [p["data"] for p in posts]
```

- **Rate limit:** ~60 requests/minute without auth — workable for batch scraping
- **Depth:** Up to ~1000 posts per subreddit per sort (top/new/hot)
- **Risk:** Reddit can block scrapers; use a respectful User-Agent and rate limit aggressively
- **Best for:** Supplementing Arctic Shift with fresher posts

---

### 3. Google/Bing Scoped Search (Tertiary — Free tier available)
Search engines index Reddit. Scoping to `site:reddit.com` returns top posts without touching Reddit's infrastructure.

```python
# Using SerpAPI or similar
query = "site:reddit.com/r/JapanTravel best ramen tokyo"
# Returns top Reddit results without any Reddit auth
```

- **Use case:** Targeted venue research rather than bulk corpus scraping
- **Cost:** SerpAPI free tier is 100 searches/month; paid tier ~$50/mo for 5K searches
- **Best for:** Filling gaps on specific venues during city seeding

---

### 4. Apify Reddit Scraper (~$30/month)
Managed scraping service that handles bot detection, rate limiting, and JS rendering. Produces structured output.

- **URL:** `apify.com/apify/reddit-scraper`
- **Cost:** ~$30/mo at bootstrap scale
- **Output:** Structured JSON — maps cleanly to the existing pipeline
- **Best for:** If direct scraping gets blocked and Arctic Shift isn't sufficient

---

### 5. Official API — Enterprise (Future)
When Overplanned has meaningful user scale, Reddit's Data API enterprise tier becomes viable. They negotiate pricing based on usage. Not a day-one consideration.

---

## What Doesn't Change

The bootstrap pipeline architecture is unchanged. Reddit is still Tier 1 signal quality. The access method changes, not the data or how it's used.

**Key principle stays the same:** Store only derived outputs (vibe tags, scores, entity references). Discard raw scraped content after 30 days. This keeps Overplanned compliant regardless of access method — you're not storing Reddit's content, you're storing your structured inferences from it.

**ML training clarification:** Reddit ToS restricts using their content to train ML models. Overplanned does not train on Reddit content directly. The LLM extraction pipeline reads Reddit text and outputs structured ActivityNode signals — those signals are what enter the training pipeline, not the raw Reddit content. This is the correct and defensible architecture.

---

## Recommended Approach for Launch

| Phase | Method | Cost |
|---|---|---|
| Pre-launch city seeding | Arctic Shift bulk download + direct HTTP | ~$0 |
| Ongoing freshness | Direct HTTP scraping (rate-limited) | ~$0 |
| If blocked | Apify scraper | ~$30/mo |
| At scale | Reddit enterprise API | Negotiated |

Start with Arctic Shift for historical depth, supplement with direct HTTP for recency. Apify is the fallback if Reddit tightens restrictions further.
