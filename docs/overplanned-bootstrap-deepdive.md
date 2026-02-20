**WAYMARK**

**Bootstrap Intelligence Stack**

Scraping · LLM Extraction · Vibe Tagging · ML Transition

How Overplanned populates ActivityNodes before the first user, runs a
cost-efficient LLM ranker during MVP, and transitions to learned ML
models as behavioral data accumulates.

**0. The Problem, Precisely**

Month 0. No users. No behavioral signals. No training data. The
recommendation system needs to work on day one --- but every ML model in
the architecture requires data that doesn\'t exist yet.

The three-layer bootstrap strategy resolves this without shortcuts or
synthetic hallucination:

-   Layer 1 --- Scrape: populate ActivityNode quality signals from
    existing community data before launch

-   Layer 2 --- LLM Ranker: use those signals to guide an LLM ranker
    that works immediately, logs every decision

-   Layer 3 --- Transition: as real behavioral data accumulates, ML
    models phase out the LLM ranker component by component

  --------- ---------------------------------------------------------------
  **KEY**   The LLM is never the data source. It is a ranking interface
            over pre-built structured signals. This distinction determines
            whether the system\'s local-source advantage is preserved or
            destroyed.

  --------- ---------------------------------------------------------------

**1. The Scraping Pipeline**

The goal is to pre-populate three things on every ActivityNode before a
single user opens the app: a quality_signals object (multi-source, not
collapsed), a vibe_tags array (LLM-extracted from community text), and a
cross_ref_confidence score (how many independent sources agree).

**1.1 Source Tier Map**

Not all sources are worth equal effort. Tier 1 gets built first --- high
signal, accessible access methods, worth the engineering time before
launch.

  ----------------------------------------------------------------------------------------
  **Source**    **Signal    **Access         **Coverage**     **What We Extract**
                Quality**   Method**                          
  ------------- ----------- ---------------- ---------------- ----------------------------
  Reddit (PRAW) ★★★★★       API + Pushshift  r/JapanTravel,   Overrated signal, recurring
                            archive          r/solotravel,    mentions, \'I live here\'
                                             city subs        override

  Travel blogs  ★★★★        RSS + periodic   30--50 seed      Hidden gem consensus,
  (curated)                 crawl            blogs per region specificity, cross-reference

  Tabelog,      ★★★★★       Scrape           Food + activity  Local vs tourist divergence,
  Dianping,                 (rate-limited)   per region       strict local scoring
  Naver                                                       

  2ch/5ch, DC   ★★★★        Scrape + DeepL   Japan, Korea,    Brutally honest locals. High
  Inside, Tieba             translation      China            noise ratio.

  Foursquare    ★★★         Official API     100M+ POIs       Venue metadata, check-in
  Places API                                 globally         volume, category taxonomy

  Google Places ★★★         Official API     Global coverage  Photo density, aggregate
  API                                                         score, hours

  TripAdvisor   ★           API or scrape    Global but       Useful ONLY for divergence
                                             tourist-heavy    calculation --- not quality
                                                              signal
  ----------------------------------------------------------------------------------------

**1.2 Reddit Scraping --- Implementation**

PRAW (Python Reddit API Wrapper) is the primary tool. The 2023 API
changes rate-limit to 100 requests/minute on the free tier --- workable
for pre-launch batch scraping, not for real-time. For historical depth
beyond 1000 posts per subreddit, use the Pushshift.io academic API or
the arctic-shift mirror.

**scraper/reddit_scraper.py**

> import praw
>
> import pandas as pd
>
> from datetime import datetime
>
> import time
>
> \# Subreddits by region --- expand this list before launch
>
> SUBREDDITS = {
>
> \"japan\": \[\"JapanTravel\", \"japanlife\", \"tokyo\", \"osaka\",
> \"kyoto\"\],
>
> \"korea\": \[\"koreatravel\", \"korea\", \"seoul\"\],
>
> \"china\": \[\"China_travel\", \"shanghai\", \"beijing\"\],
>
> \"global\": \[\"travel\", \"solotravel\", \"backpacking\",
> \"foodtravel\"\],
>
> \"cities\": \[\"paris\", \"london\", \"bangkok\", \"bali\", \"nyc\",
> \"singapore\"\],
>
> }
>
> \# Signals we care about --- filter aggressively
>
> EXTRACT_PATTERNS = {
>
> \"local_override\": \[\"i live here\", \"as a local\", \"locals go
> to\", \"tourists don\'t know\"\],
>
> \"overrated_signal\": \[\"overrated\", \"not worth it\", \"skip it\",
> \"tourist trap\"\],
>
> \"hidden_gem\": \[\"hidden gem\", \"off the beaten\", \"secret\",
> \"underrated\", \"don\'t tell anyone\"\],
>
> \"recurring_mention\": \[\], \# detected by cross-reference at
> aggregation step
>
> }
>
> class RedditScraper:
>
> def \_\_init\_\_(self, client_id, client_secret, user_agent):
>
> self.reddit = praw.Reddit(
>
> client_id=client_id,
>
> client_secret=client_secret,
>
> user_agent=user_agent
>
> )
>
> def scrape_subreddit(self, subreddit_name, limit=1000, sort=\"top\"):
>
> sub = self.reddit.subreddit(subreddit_name)
>
> posts = \[\]
>
> comments = \[\]
>
> fetcher = getattr(sub, sort)(limit=limit, time_filter=\"all\")
>
> for post in fetcher:
>
> posts.append({
>
> \"id\": post.id,
>
> \"subreddit\": subreddit_name,
>
> \"title\": post.title,
>
> \"body\": post.selftext,
>
> \"score\": post.score,
>
> \"upvote_ratio\": post.upvote_ratio,
>
> \"num_comments\": post.num_comments,
>
> \"created_utc\": post.created_utc,
>
> \"url\": post.url,
>
> \"flair\": post.link_flair_text,
>
> })
>
> \# Fetch top-level comments (depth=1 for efficiency)
>
> post.comments.replace_more(limit=0) \# skip MoreComments
>
> for comment in post.comments.list()\[:50\]: \# cap at 50/post
>
> comments.append({
>
> \"post_id\": post.id,
>
> \"comment_id\": comment.id,
>
> \"body\": comment.body,
>
> \"score\": comment.score,
>
> \"created_utc\": comment.created_utc,
>
> \"is_local\": any(p in comment.body.lower()
>
> for p in EXTRACT_PATTERNS\[\"local_override\"\]),
>
> })
>
> time.sleep(0.6) \# respect rate limits
>
> return pd.DataFrame(posts), pd.DataFrame(comments)
>
> def scrape_all_regions(self, output_dir=\"data/raw/reddit\"):
>
> for region, subs in SUBREDDITS.items():
>
> for sub_name in subs:
>
> print(f\"Scraping r/{sub_name}\...\")
>
> posts_df, comments_df = self.scrape_subreddit(sub_name)
>
> posts_df.to_parquet(f\"{output_dir}/{region}\_{sub_name}\_posts.parquet\")
>
> comments_df.to_parquet(f\"{output_dir}/{region}\_{sub_name}\_comments.parquet\")
>
> time.sleep(2) \# between subreddits

Key implementation notes: always filter posts by upvote_ratio \> 0.7 and
score \> 10 before LLM extraction --- you don\'t want to spend
extraction budget on downvoted noise. Local override comments
(is_local=True) get flagged separately and carry 3x signal weight in the
cross-reference scorer.

**1.3 Blog Scraping --- Curated Seed List**

The temptation is to scrape all travel blogs. Resist it. The SEO spam
ratio is roughly 85:15 junk:signal. Instead, maintain a curated seed
list of \~30--50 high-authority blogs per region, evaluated once by hand
against the blogger authority model (temporal depth, specificity, local
knowledge, low affiliate density).

**scraper/blog_scraper.py**

> import feedparser
>
> import requests
>
> from bs4 import BeautifulSoup
>
> import hashlib
>
> from urllib.parse import urlparse
>
> \# Curated seed list --- manual vetting required before adding
>
> BLOG_SEEDS = {
>
> \"japan\": \[
>
> {\"url\": \"https://www.tokyocheapo.com/feed\", \"authority\": 0.82,
> \"type\": \"rss\"},
>
> {\"url\": \"https://livejapan.com/en/feed\", \"authority\": 0.79,
> \"type\": \"rss\"},
>
> \# expand\...
>
> \],
>
> \"southeast_asia\": \[
>
> \# expand\...
>
> \],
>
> }
>
> \# Authority signals --- computed once at seed evaluation
>
> AUTHORITY_SIGNALS = {
>
> \"temporal_depth\": 0.30, \# posts span 3+ years in same region
>
> \"specificity\": 0.25, \# mentions specific streets, seasonal timing
>
> \"local_language\": 0.20, \# writes in local language or
> resident-authored
>
> \"cross_ref_freq\": 0.15, \# cited by other credible blogs/forums
>
> \"affiliate_ratio\": -0.10, \# penalize affiliate link density
>
> }
>
> class BlogScraper:
>
> def \_\_init\_\_(self):
>
> self.seen_urls = set()
>
> def scrape_feed(self, feed_config):
>
> feed = feedparser.parse(feed_config\[\"url\"\])
>
> posts = \[\]
>
> for entry in feed.entries:
>
> url = entry.get(\"link\", \"\")
>
> if url in self.seen_urls:
>
> continue
>
> self.seen_urls.add(url)
>
> content = self.\_fetch_content(url)
>
> if content is None:
>
> continue
>
> posts.append({
>
> \"url\": url,
>
> \"title\": entry.get(\"title\", \"\"),
>
> \"content\": content,
>
> \"published\": entry.get(\"published\", \"\"),
>
> \"source_authority\": feed_config\[\"authority\"\],
>
> \"content_hash\": hashlib.md5(content.encode()).hexdigest(),
>
> \"word_count\": len(content.split()),
>
> })
>
> return posts
>
> def \_fetch_content(self, url):
>
> try:
>
> resp = requests.get(url, timeout=10, headers={
>
> \"User-Agent\": \"Overplanned-Research-Bot/1.0\"
>
> })
>
> soup = BeautifulSoup(resp.content, \"html.parser\")
>
> \# Target article body --- adjust selector per site
>
> article = soup.find(\"article\") or
> soup.find(class\_=\"post-content\")
>
> return article.get_text(separator=\" \") if article else None
>
> except Exception:
>
> return None

**1.4 Local Platform Scraping --- Tabelog et al.**

Tabelog, Dianping, and Naver are the crown jewels but actively resist
scraping. They implement bot detection via user-agent checking, rate
limiting, and occasionally JS-rendered content. The pragmatic approach
for pre-launch: scrape venue-level aggregate scores only (not review
text), using a rotating proxy pool and human-like request timing. Review
text at scale requires API access (limited/paid) or a more
resource-intensive scrape that\'s better deferred to post-launch.

**scraper/local_platform_scraper.py**

> import cloudscraper \# handles JS challenges better than requests
>
> import time, random
>
> from typing import Optional
>
> class TabelogScraper:
>
> \"\"\"
>
> Scrapes aggregate scores only --- not review text.
>
> Aggregate scores are sufficient for quality_signals pre-launch.
>
> Review text requires API or heavier scrape --- defer to post-launch.
>
> \"\"\"
>
> BASE = \"https://tabelog.com\"
>
> def \_\_init\_\_(self, proxy_list: list):
>
> self.proxies = proxy_list
>
> self.scraper = cloudscraper.create_scraper()
>
> def \_get_proxy(self):
>
> return {\"https\": random.choice(self.proxies)}
>
> def scrape_venue(self, tabelog_url: str) -\> Optional\[dict\]:
>
> try:
>
> time.sleep(random.uniform(2.5, 6.0)) \# human-like timing
>
> resp = self.scraper.get(
>
> tabelog_url,
>
> proxies=self.\_get_proxy(),
>
> headers={\"Accept-Language\": \"ja-JP,ja;q=0.9\"}
>
> )
>
> from bs4 import BeautifulSoup
>
> soup = BeautifulSoup(resp.text, \"html.parser\")
>
> score_el = soup.select_one(\".rdheader-rating\_\_score-val-dtl\")
>
> review_count_el =
> soup.select_one(\".rdheader-rating\_\_review-count\")
>
> price_el = soup.select_one(\".rdheader-budget-val\")
>
> genre_el = soup.select_one(\".rdheader-subinfo-genre\")
>
> return {
>
> \"tabelog_url\": tabelog_url,
>
> \"tabelog_score\": float(score_el.text.strip()) if score_el else None,
>
> \"review_count\":
> int(review_count_el.text.replace(\",\",\"\").strip())
>
> if review_count_el else None,
>
> \"price_range\": price_el.text.strip() if price_el else None,
>
> \"genre\": genre_el.text.strip() if genre_el else None,
>
> \"source\": \"tabelog\",
>
> \"scraped_at\": time.time(),
>
> }
>
> except Exception as e:
>
> print(f\"Failed {tabelog_url}: {e}\")
>
> return None

  ---------- ---------------------------------------------------------------
  **NOTE**   For China (Dianping) and Korea (Naver), the scraping logic is
             structurally identical but requires DeepL API translation of
             category labels and a VPN-aware proxy pool for China. Budget
             \~\$20-30/month for DeepL at pre-launch scale.

  ---------- ---------------------------------------------------------------

**1.5 The English-Weight Problem**

This is the most important architectural decision in the entire scraping
pipeline. When you aggregate signals from Reddit, English blogs, and
TripAdvisor, you are encoding a specific demographic\'s preferences as
your prior --- Western travelers, higher budget, Instagram-era
aesthetic. This bias will persist into your ML models unless you
deliberately separate it.

Never collapse to a single quality_score. Always store signals by source
type:

**models/activity_node.py --- quality_signals structure**

> \# On ActivityNode --- never a single merged score
>
> quality_signals = {
>
> \# English / tourist-facing sources
>
> \"en_reddit_score\": 0.82, \# r/JapanTravel consensus
>
> \"en_blog_score\": 0.74, \# curated blogger corpus
>
> \"tripadvisor_score\": 0.88, \# tourist aggregator (divergence calc
> only)
>
> \# Local / region-specific sources
>
> \"tabelog_score\": 3.71, \# 0--5 Tabelog scale (Japan only)
>
> \"naver_score\": 4.2, \# 1--5 Naver (Korea only)
>
> \"dianping_score\": None, \# null if not applicable
>
> \"local_forum_score\": 0.77, \# 2ch/5ch/DC Inside normalized 0--1
>
> \# Derived signals
>
> \"tourist_local_divergence\": +0.14, \# positive = tourists love,
> locals meh
>
> \"cross_ref_confidence\": 0.91, \# how many independent sources agree
>
> \"overrated_flag\": False, \# divergence \> 0.3 threshold
>
> \# Source metadata
>
> \"local_review_count\": 847,
>
> \"tourist_review_count\": 2341,
>
> \"last_updated\": \"2025-01-15\",
>
> }
>
> \# The LLM ranker and ML model receive ALL of these as separate
> features.
>
> \# The weighting by persona happens at ranking time --- not at storage
> time.
>
> \#
>
> \# persona=\"city_boy_local_foodie\" → weight tabelog_score 1.0,
> en_reddit_score 0.3
>
> \# persona=\"first_time_tourist\" → weight en_reddit_score 0.8,
> tabelog_score 0.5

This separation is what allows the system to learn, over time, which
source weights actually predict acceptance for each persona type. If you
collapse to one score, you permanently encode the bias of whoever built
the weighting function.

**2. LLM Extraction --- Signal Pull from Text**

The scraped corpus is raw text. ActivityNodes need structured signals.
The LLM extraction pipeline converts messy community posts into
structured data at batch scale --- cheaply, without real-time inference.

**2.1 What We\'re Extracting**

From every venue mention in the corpus, we want to extract:

-   Venue name, city, category (structured)

-   Vibe tags: an array of 3--8 descriptors from a controlled vocabulary

-   Sentiment: positive / neutral / negative toward this venue

-   Author type: tourist / local-resident / expat / unknown

-   Explicit recommendation: boolean --- did the author directly
    recommend it?

-   Overrated flag: boolean --- did the author call it overrated or a
    tourist trap?

-   Crowd notes: any mention of busyness, wait times, best visiting
    times

-   Price signal: any price indication (cheap/mid/expensive/price
    ranges)

**2.2 Vibe Vocabulary --- Controlled, Not Open**

The most important design decision in LLM extraction: use a controlled
vibe vocabulary, not free-form tagging. Open-ended tagging gives you 500
variations of \'cozy\' (\'cozy\', \'chill\', \'relaxed\', \'laid-back\',
\'mellow\', etc.) that are impossible to compare across sources or embed
consistently.

Define the vocabulary once, upfront. The LLM must select from it, not
invent:

**config/vibe_vocab.py**

> \# Controlled vibe vocabulary --- \~60 tags across 6 dimensions
>
> \# The LLM must select only from this list. No free-form tags.
>
> VIBE_VOCAB = {
>
> \# Energy level
>
> \"energy\": \[
>
> \"high-energy\", \"lively\", \"buzzing\",
>
> \"moderate-pace\", \"relaxed\", \"slow-burn\",
>
> \"quiet\", \"serene\",
>
> \],
>
> \# Social context
>
> \"social\": \[
>
> \"solo-friendly\", \"couples\", \"group-friendly\",
>
> \"family-ok\", \"date-night\", \"work-from\",
>
> \"social-scene\", \"people-watching\",
>
> \],
>
> \# Local authenticity
>
> \"authenticity\": \[
>
> \"locals-only\", \"mostly-local\", \"mixed-crowd\",
>
> \"tourist-friendly\", \"tourist-heavy\",
>
> \],
>
> \# Sensory / aesthetic
>
> \"aesthetic\": \[
>
> \"minimalist\", \"traditional\", \"modern\",
>
> \"outdoor\", \"indoor\", \"rooftop\",
>
> \"scenic-view\", \"hidden-alley\", \"market-style\",
>
> \],
>
> \# Time fit
>
> \"timing\": \[
>
> \"morning-best\", \"lunch-spot\", \"afternoon\",
>
> \"evening\", \"late-night\", \"all-day\",
>
> \"seasonal\", \"weekday-only\",
>
> \],
>
> \# Cost signal
>
> \"cost\": \[
>
> \"budget\", \"mid-range\", \"splurge\",
>
> \"free\", \"pay-what-you-want\",
>
> \],
>
> }
>
> \# All valid tags --- flattened for validation
>
> ALL_VIBE_TAGS = \[tag for tags in VIBE_VOCAB.values() for tag in
> tags\]

**2.3 Extraction Prompt --- Optimized for Token Efficiency**

The extraction prompt is the single biggest cost lever. Every
unnecessary token in the prompt multiplies across the entire corpus. The
principles for minimum-token extraction prompts:

-   System prompt once, reused across entire batch --- never repeat
    instructions per item

-   JSON schema in system prompt as reference --- don\'t explain it in
    natural language

-   Controlled vocabulary in system prompt --- LLM doesn\'t need to
    generate tag names

-   Process multiple venue mentions per call --- batch within a single
    post

-   Short output schema --- every field name counts at scale

**extraction/prompt.py**

> SYSTEM_PROMPT = \"\"\"You are a travel data extractor. Extract venue
> mentions from travel text.
>
> Output: JSON array only. No explanation. No markdown. No preamble.
>
> Schema per venue:
>
> {\"n\":\"venue
> name\",\"c\":\"city\",\"cat\":\"food\|bar\|activity\|accommodation\|other\",
>
> \"v\":\[\"vibe tags from list
> below\"\],\"s\":1\|0\|-1,\"auth\":\"local\|tourist\|expat\|unknown\",
>
> \"rec\":true\|false,\"ov\":true\|false,\"crowd\":\"string or
> null\",\"price\":\"cheap\|mid\|exp\|null\"}
>
> Vibe tags (select 2-8 only from this list):
>
> high-energy,lively,buzzing,moderate-pace,relaxed,slow-burn,quiet,serene,
>
> solo-friendly,couples,group-friendly,family-ok,date-night,work-from,social-scene,people-watching,
>
> locals-only,mostly-local,mixed-crowd,tourist-friendly,tourist-heavy,
>
> minimalist,traditional,modern,outdoor,indoor,rooftop,scenic-view,hidden-alley,market-style,
>
> morning-best,lunch-spot,afternoon,evening,late-night,all-day,seasonal,weekday-only,
>
> budget,mid-range,splurge,free,pay-what-you-want
>
> Rules:
>
> \- s: 1=positive, 0=neutral, -1=negative
>
> \- ov: true only if author explicitly calls it overrated or tourist
> trap
>
> \- Only extract venues explicitly named. Skip vague references.
>
> \- If no venues found, return \[\]\"\"\"
>
> def build_extraction_prompt(post_text: str, max_chars: int = 1200) -\>
> str:
>
> \# Truncate long posts --- most signal is in first 1200 chars
>
> truncated = post_text\[:max_chars\]
>
> return truncated \# system prompt handles the rest
>
> \# Token estimate per call:
>
> \# System prompt: \~380 tokens (fixed, amortized across batch)
>
> \# Input per post: \~300 tokens average (after truncation)
>
> \# Output per post: \~150 tokens average (3-4 venues, compact JSON)
>
> \# Total per post: \~830 tokens with system prompt amortization in
> batch mode

**2.4 Batch Processing --- The Primary Cost Lever**

This is where you cut costs by 50--60% compared to naive per-call
extraction. Anthropic\'s Batch API processes requests asynchronously at
half the per-token price, with 24-hour turnaround. For pre-launch corpus
processing, this is the only sensible approach.

**extraction/batch_processor.py**

> import anthropic
>
> import json
>
> from pathlib import Path
>
> client = anthropic.Anthropic()
>
> def prepare_batch(posts: list\[dict\], batch_id: str) -\>
> list\[dict\]:
>
> \"\"\"
>
> Prepare a batch of posts for Anthropic Batch API.
>
> One request per post --- system prompt shared implicitly via API.
>
> \"\"\"
>
> requests = \[\]
>
> for i, post in enumerate(posts):
>
> \# Skip low-signal posts before spending tokens
>
> if post.get(\"score\", 0) \< 10 or post.get(\"upvote_ratio\", 0) \<
> 0.7:
>
> continue
>
> if len(post.get(\"body\", \"\")) \< 50:
>
> continue
>
> requests.append({
>
> \"custom_id\": f\"{batch_id}\_{i}\_{post\[\'id\'\]}\",
>
> \"params\": {
>
> \"model\": \"claude-haiku-4-5-20251001\", \# cheapest, sufficient for
> extraction
>
> \"max_tokens\": 512,
>
> \"system\": SYSTEM_PROMPT,
>
> \"messages\": \[{\"role\": \"user\", \"content\":
> post\[\"body\"\]\[:1200\]}\]
>
> }
>
> })
>
> return requests
>
> def submit_batch(requests: list\[dict\]) -\> str:
>
> batch = client.beta.messages.batches.create(requests=requests)
>
> return batch.id
>
> def poll_and_collect(batch_id: str, output_path: str):
>
> \"\"\"Poll until complete, then collect results.\"\"\"
>
> import time
>
> while True:
>
> batch = client.beta.messages.batches.retrieve(batch_id)
>
> if batch.processing_status == \"ended\":
>
> break
>
> print(f\"Batch {batch_id}: {batch.request_counts}\")
>
> time.sleep(60)
>
> results = \[\]
>
> for result in client.beta.messages.batches.results(batch_id):
>
> if result.result.type == \"succeeded\":
>
> try:
>
> content = result.result.message.content\[0\].text
>
> venues = json.loads(content)
>
> results.append({
>
> \"custom_id\": result.custom_id,
>
> \"venues\": venues
>
> })
>
> except json.JSONDecodeError:
>
> pass \# malformed --- skip
>
> with open(output_path, \"w\") as f:
>
> json.dump(results, f)
>
> return results
>
> \# Cost math at batch pricing (50% discount vs standard):
>
> \# claude-haiku-4-5-20251001 batch: \$0.00025/1K input, \$0.00125/1K
> output
>
> \# 100K posts × 830 tokens avg = 83M tokens
>
> \# 83M input × \$0.00025/1K = \$20.75
>
> \# 83M output × 0.18 ratio × \$0.00125/1K = \~\$18.70
>
> \# TOTAL pre-launch corpus: \~\$40 for 100K posts
>
> \# vs standard API: \~\$80 --- batch saves 50%

  ---------- ---------------------------------------------------------------
  **COST**   Pre-launch extraction of 100K Reddit posts + blog posts at
             batch pricing: \~\$40 total. This is a one-time cost. Monthly
             re-processing of new content: \~\$4--8/month depending on
             volume growth.

  ---------- ---------------------------------------------------------------

**2.5 Token Reduction Techniques --- Ranking Calls**

The batch processing above handles pre-launch corpus extraction. The
live LLM ranker (serving users during MVP) is a different cost profile
--- it runs in real-time and can\'t use batch pricing. Here\'s how to
minimize tokens per ranking call:

+-------------------------------+--------------------------------------+
| **Technique 1: Structured     | **Technique 2: Compressed Persona**  |
| Candidates**                  |                                      |
|                               | Don\'t send the full user profile.   |
| Don\'t send full ActivityNode | Send a 5-field persona summary       |
| records to the LLM. Send a    | derived from the full profile:       |
| compressed candidate schema   |                                      |
| that contains only what the   | > // Full user profile: \~600 tokens |
| LLM needs for ranking:        | > // Compressed: \~80 tokens         |
|                               | > {\"persona                         |
| > // Full ActivityNode: \~800 | \":\"city_boy\",\"energy\":\"high\", |
| > tokens // Compressed        | \"budget\":\"mid\",\"local_pref\":0. |
| > candidate: \~90 tokens      | 85,\"trip_style\":\"solo_explorer\"} |
| > {\"id\":\"ax_881\",\"n      |                                      |
| \":\"Kikanbo\",\"cat\":\"food | The LLM doesn\'t need raw behavioral |
| \",\"v\":\[\"high-energy\",\" | history for ranking. It needs the    |
| locals-only\",\"budget\"\],\" | interpreted persona. The persona     |
| tourist\":0.12,\"score\":0.88 | engine handles interpretation; the   |
| ,\"dur\":45,\"cost\":\"mid\"} | LLM just applies it.                 |
|                               |                                      |
| Reduction: 800 → 90 tokens    |                                      |
| per candidate. At 20          |                                      |
| candidates per ranking call:  |                                      |
| 16,000 → 1,800 tokens. 89%    |                                      |
| reduction on candidate input. |                                      |
+-------------------------------+--------------------------------------+

**ranker/llm_ranker.py --- compressed ranking call**

> RANKER_SYSTEM = \"\"\"Rank travel activities for a user. Output JSON
> array of IDs only.
>
> No explanation. Format: {\"ranked\":\[\"id1\",\"id2\",\...\]}\"\"\"
>
> def build_ranking_prompt(user_persona: dict, candidates: list\[dict\])
> -\> tuple\[str, int\]:
>
> \"\"\"
>
> Builds a minimum-token ranking prompt.
>
> Returns (prompt_string, estimated_tokens).
>
> \"\"\"
>
> \# Compress persona to 5 fields
>
> persona_compact = {
>
> \"p\": user_persona\[\"primary_persona\"\], \# e.g. \"city_boy\"
>
> \"e\": user_persona\[\"energy_level\"\], \# \"high\" \| \"mid\" \|
> \"low\"
>
> \"b\": user_persona\[\"budget_tier\"\], \# \"budget\" \| \"mid\" \|
> \"splurge\"
>
> \"l\": round(user_persona\[\"local_pref\"\], 2), \# 0-1
>
> \"s\": user_persona\[\"trip_style\"\], \# \"solo\" \| \"couple\" \|
> \"group\"
>
> }
>
> \# Compress each candidate to minimum fields
>
> candidates_compact = \[{
>
> \"id\": c\[\"id\"\],
>
> \"n\": c\[\"name\"\]\[:30\], \# truncate long names
>
> \"cat\": c\[\"category\"\],
>
> \"v\": c\[\"vibe_tags\"\]\[:4\], \# max 4 vibe tags
>
> \"t\": round(c\[\"tourist_score\"\], 2),
>
> \"q\": round(c\[\"quality_score\"\], 2),
>
> \"dur\": c\[\"typical_duration_min\"\],
>
> } for c in candidates\]
>
> prompt = f\"User:{json.dumps(persona_compact)}
>
> Activities:{json.dumps(candidates_compact)}\"
>
> \# Token estimate: persona \~50, candidates \~90 each, structure \~30
>
> estimated_tokens = 50 + (len(candidates) \* 90) + 30
>
> return prompt, estimated_tokens
>
> \# Per-call cost at standard pricing (haiku):
>
> \# System: \~120 tokens (fixed)
>
> \# User message: \~1850 tokens (50 persona + 20 candidates × 90)
>
> \# Output: \~80 tokens (ranked IDs array)
>
> \# Total: \~2050 tokens per ranking call
>
> \# Cost per call: (2050/1000) × \$0.0008 = \$0.0016
>
> \# At 500 MAU × 3 trips × 1 ranking call = 1500 calls/month =
> \$2.40/month

**2.6 Caching --- The Silent Cost Killer**

A significant fraction of ranking calls are redundant. The same user
persona against similar candidate pools in the same city produces very
similar rankings. Cache aggressively at two levels:

**ranker/cache.py**

> import hashlib, json
>
> from redis import Redis
>
> redis = Redis()
>
> def ranking_cache_key(persona: dict, candidate_ids: list, context:
> dict) -\> str:
>
> \"\"\"
>
> Cache key is a hash of:
>
> \- Persona archetype (not exact scores --- archetypes change rarely)
>
> \- Sorted candidate IDs (order-insensitive)
>
> \- Coarse context: city, day_part (morning/afternoon/evening),
> trip_day_number
>
> \"\"\"
>
> persona_archetype = {
>
> \"persona\": persona\[\"primary_persona\"\],
>
> \"energy\": persona\[\"energy_level\"\],
>
> \"budget\": persona\[\"budget_tier\"\],
>
> }
>
> context_coarse = {
>
> \"city\": context\[\"city\"\],
>
> \"day_part\": context\[\"day_part\"\], \# morning \| afternoon \|
> evening
>
> \"trip_day\": min(context\[\"trip_day_number\"\], 5), \# cap at 5 ---
> day 6+ same as day 5
>
> }
>
> key_data = {
>
> \"persona\": persona_archetype,
>
> \"candidates\": sorted(candidate_ids),
>
> \"context\": context_coarse,
>
> }
>
> key_str = json.dumps(key_data, sort_keys=True)
>
> return f\"rank:{hashlib.md5(key_str.encode()).hexdigest()}\"
>
> def get_cached_ranking(key: str) -\> list \| None:
>
> val = redis.get(key)
>
> return json.loads(val) if val else None
>
> def cache_ranking(key: str, ranked_ids: list, ttl_seconds: int = 3600
> \* 6):
>
> \"\"\"Cache for 6 hours --- persona doesn\'t change that fast.\"\"\"
>
> redis.setex(key, ttl_seconds, json.dumps(ranked_ids))
>
> \# Cache hit rate at MVP scale with 500 users:
>
> \# Same city, similar persona types, limited candidate pool → \~35-45%
> cache hit rate
>
> \# Effective LLM calls: 55-65% of total requests
>
> \# With 35% cache hit: cost drops from \$2.40 to \~\$1.56/month at MVP
> scale

**2.7 Full Cost Model --- Month 0 to Month 9**

  ---------------------------------------------------------------------------------
  **Stage**          **Volume**   **Model +        **Ranking     **Notes**
                                  Strategy**       Cost**        
  ------------------ ------------ ---------------- ------------- ------------------
  Pre-launch corpus  100K posts   Batch API, Haiku \~\$40        \~\$40 total
  (one-time)                                                     

  MVP serving, 100   300 trips/mo Standard API,    \~\$0.48/mo   \~\$5.76/yr
  MAU                             Haiku + cache                  

  MVP serving, 500   1,500        Standard API,    \~\$2.40/mo   \~\$28.80/yr
  MAU                trips/mo     Haiku + cache                  

  MVP serving, 2K    6,000        Standard API,    \~\$5.76/mo   \~\$69/yr
  MAU                trips/mo     Haiku + 40%                    
                                  cache                          

  ML transition, 500 1,500        LLM cold-start   \~\$0.48/mo   On ML model
  MAU                trips/mo     only (\<20%)                   

  Post-transition,   15,000       LLM narrative    \~\$4.80/mo   ML handles ranking
  5K MAU             trips/mo     layer only                     
  ---------------------------------------------------------------------------------

  --------- ---------------------------------------------------------------
  **KEY**   The LLM ranking cost stays under \$10/month through the first
            2,000 MAU. The transition to ML ranking is driven by quality
            improvement, not cost pressure --- but at 5K+ MAU, the cost
            savings become material.

  --------- ---------------------------------------------------------------

**3. Vibe Tagger Architecture**

The vibe tagger is the bridge between raw community text and the
vibe_embedding stored on every ActivityNode. It has two jobs: (1)
extract vibe tags from scraped corpus at batch scale pre-launch, and (2)
as behavioral data accumulates, learn a regression model that maps raw
text → vibe embedding directly without LLM inference.

**3.1 Architecture Overview**

**Vibe tagging --- two-phase architecture**

> Phase 1 (pre-launch, Month 0):
>
> Scraped text → LLM batch extraction → controlled vibe tags → store on
> ActivityNode
>
> Cost: \~\$40 one-time. Latency: 24hr batch turnaround.
>
> Phase 2 (Month 3+, once tags accumulate):
>
> Text → sentence-transformers embedding → small MLP → vibe embedding
> (64-dim)
>
> Cost: essentially free (CPU inference). Latency: \<10ms.
>
> The Phase 2 model is trained on Phase 1\'s LLM-extracted tags as
> labels.
>
> This is the \"LLM as teacher, small model as student\" pattern ---
> distillation.

**3.2 Phase 1 --- LLM Tag Extraction at Scale**

Already covered in Section 2 --- the batch extraction pipeline produces
controlled vibe tags per venue mention. The aggregation step is what
turns per-mention tags into per-ActivityNode vibe signals:

**extraction/vibe_aggregator.py**

> from collections import Counter
>
> import numpy as np
>
> def aggregate_vibe_tags(venue_mentions: list\[dict\]) -\> dict:
>
> \"\"\"
>
> Aggregates LLM-extracted tags across all mentions of a venue.
>
> Weights by source authority and local/tourist author type.
>
> \"\"\"
>
> tag_scores = Counter()
>
> tag_weights = Counter()
>
> for mention in venue_mentions:
>
> source_authority = mention.get(\"source_authority\", 0.5)
>
> author_weight = {
>
> \"local\": 2.0, \# locals get 2x weight
>
> \"expat\": 1.5,
>
> \"tourist\": 0.8,
>
> \"unknown\": 1.0,
>
> }.get(mention.get(\"auth\", \"unknown\"), 1.0)
>
> weight = source_authority \* author_weight
>
> for tag in mention.get(\"vibe_tags\", \[\]):
>
> tag_scores\[tag\] += weight
>
> tag_weights\[tag\] += 1
>
> \# Normalize scores
>
> total_weight = sum(tag_scores.values())
>
> if total_weight == 0:
>
> return {\"vibe_tags\": \[\], \"vibe_confidence\": 0.0}
>
> \# Keep tags that appear in \>= 2 sources or have normalized score \>
> 0.1
>
> normalized = {tag: score / total_weight for tag, score in
> tag_scores.items()}
>
> strong_tags = \[
>
> tag for tag, score in sorted(normalized.items(), key=lambda x:
> -x\[1\])
>
> if tag_weights\[tag\] \>= 2 or score \> 0.1
>
> \]\[:8\] \# max 8 tags per venue
>
> \# Confidence = harmonic of source diversity and mention count
>
> source_diversity = len(set(m\[\"source_type\"\] for m in
> venue_mentions)) / 5.0 \# cap at 5
>
> mention_count_signal = min(len(venue_mentions) / 20.0, 1.0) \# cap at
> 20
>
> confidence = (2 \* source_diversity \* mention_count_signal) /
> (source_diversity + mention_count_signal + 1e-8)
>
> return {
>
> \"vibe_tags\": strong_tags,
>
> \"vibe_confidence\": round(confidence, 3),
>
> \"tag_counts\": dict(tag_weights),
>
> \"mention_count\": len(venue_mentions),
>
> \"local_mention_ratio\": sum(1 for m in venue_mentions if
> m.get(\"auth\") == \"local\") / len(venue_mentions),
>
> }

**3.3 Phase 2 --- Learned Vibe Tagger (Month 3+)**

Once \~500 venues have LLM-extracted vibe tags with reasonable
confidence, train a small MLP that can tag new venues from text
directly. This replaces LLM extraction for ongoing ActivityNode updates
--- dramatically cheaper and faster.

**models/vibe_tagger.py**

> import torch
>
> import torch.nn as nn
>
> from sentence_transformers import SentenceTransformer
>
> from typing import Optional
>
> class VibeTaggerModel(nn.Module):
>
> \"\"\"
>
> Text → vibe embedding (64-dim).
>
> Input: raw text from any source (blog, review, forum post)
>
> Output: 64-dim vibe embedding in the same space as item tower
>
> Training labels: LLM-extracted vibe tags (Phase 1 output)
>
> Training data: 500+ venues with LLM tags + their source text
>
> \"\"\"
>
> def \_\_init\_\_(self, input_dim: int = 384, hidden_dim: int = 256,
> output_dim: int = 64):
>
> super().\_\_init\_\_()
>
> self.encoder = SentenceTransformer(\"all-MiniLM-L6-v2\") \# 384-dim,
> CPU-friendly
>
> self.mlp = nn.Sequential(
>
> nn.Linear(input_dim, hidden_dim),
>
> nn.ReLU(),
>
> nn.Dropout(0.2),
>
> nn.Linear(hidden_dim, output_dim),
>
> )
>
> \# Multi-label head: one sigmoid per vibe tag
>
> self.tag_head = nn.Linear(output_dim, len(ALL_VIBE_TAGS))
>
> def forward(self, texts: list\[str\]):
>
> with torch.no_grad():
>
> text_embeddings = self.encoder.encode(texts, convert_to_tensor=True)
>
> vibe_embedding = self.mlp(text_embeddings)
>
> tag_logits = self.tag_head(vibe_embedding)
>
> return vibe_embedding, torch.sigmoid(tag_logits)
>
> def predict_tags(self, text: str, threshold: float = 0.4) -\>
> list\[str\]:
>
> self.eval()
>
> with torch.no_grad():
>
> \_, tag_probs = self.forward(\[text\])
>
> tag_indices = (tag_probs\[0\] \>
> threshold).nonzero(as_tuple=True)\[0\]
>
> return \[ALL_VIBE_TAGS\[i\] for i in tag_indices.tolist()\]
>
> def train_vibe_tagger(
>
> venues_with_tags: list\[dict\], \# LLM-extracted tags as labels
>
> epochs: int = 20,
>
> lr: float = 1e-3,
>
> ) -\> VibeTaggerModel:
>
> model = VibeTaggerModel()
>
> optimizer = torch.optim.Adam(model.mlp.parameters(), lr=lr) \# freeze
> encoder
>
> criterion = nn.BCELoss()
>
> for epoch in range(epochs):
>
> total_loss = 0.0
>
> for venue in venues_with_tags:
>
> texts = \[venue\[\"description_text\"\]\] \# aggregated text from all
> mentions
>
> tags = venue\[\"vibe_tags\"\] \# LLM-extracted labels
>
> \# Build multi-hot label vector
>
> label = torch.zeros(len(ALL_VIBE_TAGS))
>
> for tag in tags:
>
> if tag in ALL_VIBE_TAGS:
>
> label\[ALL_VIBE_TAGS.index(tag)\] = 1.0
>
> \_, tag_probs = model(texts)
>
> loss = criterion(tag_probs\[0\], label)
>
> optimizer.zero_grad()
>
> loss.backward()
>
> optimizer.step()
>
> total_loss += loss.item()
>
> if epoch % 5 == 0:
>
> print(f\"Epoch {epoch}: loss={total_loss/len(venues_with_tags):.4f}\")
>
> return model
>
> \# Training cost: zero GPU required for \<5K venues.
>
> \# MiniLM-L6 encoder is 22M params --- runs comfortably on CPU.
>
> \# Training time: \~15 minutes on a single CPU core for 500 venues.
>
> \# Inference: \<5ms per venue on CPU.

**3.4 Vibe Embedding Space --- Alignment with Item Tower**

The vibe_embedding on ActivityNode must live in the same 64-dimensional
space as the item tower\'s output. This alignment is what enables the
two-tower similarity search at serving time. The vibe tagger\'s
output_dim must match the item tower\'s embedding_dim --- both 64.

At pre-launch, vibe embeddings are computed from the learned tagger
applied to scraped text. When the item tower is trained on real
behavioral data (Month 5+), the vibe embedding becomes one input feature
to the tower rather than the embedding itself --- the tower learns a
better embedding from all features combined.

**models/item_tower.py --- vibe_embedding as input feature**

> class ItemTower(nn.Module):
>
> def \_\_init\_\_(self):
>
> super().\_\_init\_\_()
>
> \# Inputs include pre-computed vibe_embedding as one of many features
>
> \# At pre-launch: vibe_embedding = VibeTagger output (text-derived)
>
> \# Post-training: vibe_embedding = learned from behavioral
> co-occurrence
>
> self.fc = nn.Sequential(
>
> nn.Linear(
>
> \# Feature dimensions:
>
> 64 + \# vibe_embedding (from tagger or learned)
>
> 16 + \# category_onehot
>
> 1 + \# tourist_score (scalar)
>
> 1 + \# quality_score (scalar)
>
> 1 + \# typical_duration_min (normalized)
>
> 3 + \# cost_tier onehot (budget/mid/splurge)
>
> 16 + \# geo_cluster embedding
>
> 8, \# crowd_model features (time-of-day curve)
>
> \# = 110 total
>
> 128
>
> ),
>
> nn.ReLU(),
>
> nn.Dropout(0.2),
>
> nn.Linear(128, 64),
>
> )
>
> def forward(self, features):
>
> x = torch.cat(features, dim=-1)
>
> return nn.functional.normalize(self.fc(x), dim=-1)

**4. The LLM → ML Transition**

The transition is not a switch. It\'s a gradient. Each ML model earns
its role by demonstrating that it outperforms the LLM ranker on real
behavioral outcomes for a specific user segment. The LLM ranker retreats
component by component, not all at once.

**4.1 Transition Trigger --- The Promotion Gate**

Every ML model must clear a promotion gate before it replaces any LLM
component. The gate is:

  ---------- ---------------------------------------------------------------
  **GATE**   New model\'s HR@5 bootstrap CI lower bound must exceed LLM
             ranker\'s HR@5 CI upper bound on the same eval set. No overlap.
             This prevents false promotions in sparse data regimes.

  ---------- ---------------------------------------------------------------

**evaluation/promotion_gate.py**

> from scipy import stats
>
> import numpy as np
>
> def compute_hr_at_k(predictions: list\[list\], ground_truth: list, k:
> int = 5) -\> float:
>
> \"\"\"Hit Rate @ K --- did the user accept any of the top-K
> predictions?\"\"\"
>
> hits = sum(1 for pred, gt in zip(predictions, ground_truth)
>
> if any(p in gt for p in pred\[:k\]))
>
> return hits / len(predictions)
>
> def bootstrap_ci(data: list\[float\], n_boot: int = 1000, alpha: float
> = 0.05) -\> tuple\[float, float\]:
>
> \"\"\"Bootstrap confidence interval for HR@K.\"\"\"
>
> boots = \[np.mean(np.random.choice(data, size=len(data),
> replace=True)) for \_ in range(n_boot)\]
>
> return np.percentile(boots, 100 \* alpha / 2), np.percentile(boots,
> 100 \* (1 - alpha / 2))
>
> def promotion_gate(
>
> llm_hr_scores: list\[float\], \# HR@5 per user for LLM ranker
>
> model_hr_scores: list\[float\], \# HR@5 per user for candidate ML
> model
>
> ) -\> dict:
>
> llm_lower, llm_upper = bootstrap_ci(llm_hr_scores)
>
> model_lower, model_upper = bootstrap_ci(model_hr_scores)
>
> no_overlap = model_lower \> llm_upper
>
> improvement = np.mean(model_hr_scores) - np.mean(llm_hr_scores)
>
> return {
>
> \"llm_ci\": (round(llm_lower, 4), round(llm_upper, 4)),
>
> \"model_ci\": (round(model_lower, 4), round(model_upper, 4)),
>
> \"no_overlap\": no_overlap,
>
> \"mean_improvement\": round(improvement, 4),
>
> \"promote\": no_overlap and improvement \> 0.02, \# min 2pp
> improvement
>
> }

**4.2 The Full Transition Timeline**

  -------------------------------------------------------------------------------
  **Phase**       **Users**   **Data State**  **LLM Role**  **ML State**
  --------------- ----------- --------------- ------------- ---------------------
  Month 0--2      0--100      No behavioral   Full          Deterministic scorer
  (0--100 users)              signals         ranking +     only. Zero ML.
                                              narration     

  Month 3--4      100--300    First trips     Ranking +     BPR model trained.
  (100--300                   logged. \~2K    narration.    Not yet serving.
  users)                      behavioral      BPR trained   Shadow mode vs LLM.
                              signals.        offline.      

  Month 5 (BPR    200--400    BPR clears      Narration     BPR serves warm (3+
  gate)                       promotion gate  only. LLM     trips). LLM serves
                              on warm users.  ranking       cold users.
                                              retired for   
                                              warm users.   

  Month 6--8      300--500    Item-user       Narration +   Two-tower training
  (300--500                   co-occurrence   cold-start    begins. Shadow mode
  users)                      accumulating.   ranking only. vs BPR.

  Month 9         500+ users  Two-tower       Narration +   Two-tower serves
  (Two-tower                  clears gate on  cold-start    warm. BPR retired.
  gate)                       warm users.     only.         LLM = cold only.

  Month 12+       1K+ users   Graph density   Narration     LightGCN replaces
  (LightGCN gate)             threshold met.  only for all  two-tower for warm
                                              users.        users.
  -------------------------------------------------------------------------------

**4.3 Shadow Mode --- How Models Are Validated**

Before any model touches real users, it runs in shadow mode: the LLM
makes the live decision, but the candidate model\'s ranking is also
computed and logged. The comparison runs for 2--4 weeks until sufficient
samples accumulate for the promotion gate.

**serving/shadow_mode.py**

> class RankingOrchestrator:
>
> \"\"\"
>
> Routes ranking requests to the right model for each user segment.
>
> Handles shadow mode for models in validation.
>
> \"\"\"
>
> def \_\_init\_\_(self, llm_ranker, bpr_model=None, two_tower=None):
>
> self.llm = llm_ranker
>
> self.bpr = bpr_model
>
> self.two_tower = two_tower
>
> self.shadow_logger = ShadowLogger()
>
> def rank(self, user, candidates, context) -\> list:
>
> segment = self.\_segment(user)
>
> if segment == \"cold\":
>
> \# Always LLM for cold-start users --- no ML fallback
>
> return self.llm.rank(user, candidates, context)
>
> elif segment == \"warm_bpr_shadow\":
>
> \# BPR in shadow mode: LLM makes live decision, BPR logged
>
> live_ranking = self.llm.rank(user, candidates, context)
>
> shadow_ranking = self.bpr.rank(user, candidates, context)
>
> self.shadow_logger.log(user.id, live_ranking, shadow_ranking,
> \"bpr_shadow\")
>
> return live_ranking \# user sees LLM ranking
>
> elif segment == \"warm_bpr_live\":
>
> \# BPR promoted --- serves live, LLM in shadow
>
> live_ranking = self.bpr.rank(user, candidates, context)
>
> shadow_ranking = self.llm.rank(user, candidates, context)
>
> self.shadow_logger.log(user.id, live_ranking, shadow_ranking,
> \"llm_shadow\")
>
> return live_ranking \# user sees BPR ranking
>
> elif segment == \"warm_twotower_live\":
>
> return self.two_tower.rank(user, candidates, context)
>
> else:
>
> return self.llm.rank(user, candidates, context)
>
> def \_segment(self, user) -\> str:
>
> trips = user.completed_trips_count
>
> if trips \< 3:
>
> return \"cold\"
>
> elif self.bpr is None or not self.bpr.promoted:
>
> return \"warm_bpr_shadow\" if self.bpr else \"cold\"
>
> elif self.two_tower is None or not self.two_tower.promoted:
>
> return \"warm_bpr_live\"
>
> else:
>
> return \"warm_twotower_live\"

**4.4 LLM Ranker Retirement --- What It Never Stops Doing**

Even at Month 12 with full LightGCN serving warm users, the LLM never
fully retires. Three functions remain permanently LLM-owned:

-   Cold-start ranking: first 1--2 trips, no behavioral data,
    feature-matching only. LLM handles these indefinitely --- it\'s
    better than the alternative (random ordering).

-   Narrative generation: slot text, \'why this\' explanations, local
    tips, cultural context. This was always the LLM\'s job and the ML
    models don\'t touch it.

-   Edge cases: unusual persona combinations, first visit to an
    unrepresented city, group trips with conflicting personas. LLM as
    final fallback when confidence is low.

The practical implication: LLM cost never drops to zero, but it drops to
\~5--10% of its MVP level as a fraction of total recommendation calls.
At 10K MAU, LLM serves perhaps 1,000 cold-start trips/month instead of
10,000 total trips/month.

**4.5 Behavioral Signal Logging --- What You Must Log**

The transition pipeline fails without good logs. Every user interaction
must be captured at sufficient granularity to train the next model. The
minimum logging schema:

**logging/interaction_logger.py**

> \@dataclass
>
> class RankingEvent:
>
> \# Context
>
> user_id: str
>
> trip_id: str
>
> session_id: str
>
> timestamp: float
>
> city: str
>
> trip_day_number: int
>
> day_part: str \# morning \| afternoon \| evening
>
> \# Ranking inputs
>
> model_used: str \# \"llm\" \| \"bpr\" \| \"two_tower\" \|
> \"deterministic\"
>
> candidate_ids: list \# all candidates shown to the model
>
> ranked_ids: list \# model\'s output ranking
>
> \# User actions
>
> accepted_id: str \| None \# activity the user added to itinerary
>
> rejected_ids: list \# activities explicitly dismissed
>
> viewed_ids: list \# activities viewed but no action
>
> pivot_requested: bool \# did user ask for a swap?
>
> \# Model state
>
> persona_snapshot: dict \# compressed persona at ranking time
>
> model_version: str \# for post-hoc analysis
>
> \# Shadow data
>
> shadow_model: str \| None \# if shadow mode active
>
> shadow_ranked_ids: list \# shadow model\'s ranking
>
> \# Stored in: append-only event log (S3/GCS)
>
> \# Retention: forever --- early signals are most valuable
>
> \# Privacy: user_id is hashed; no PII stored in ranking logs

  -------------- ---------------------------------------------------------------
  **CRITICAL**   Log the full candidate set, not just the accepted item. BPR
                 training needs negative examples (what the user saw but didn\'t
                 pick). Without the candidate_ids field, you can\'t construct
                 training pairs.

  -------------- ---------------------------------------------------------------

**5. Implementation Sequence**

In the order things should be built:

  -----------------------------------------------------------------------
  **When**     **What**
  ------------ ----------------------------------------------------------
  T-8 weeks    Define vibe vocabulary (60 tags). Non-negotiable
               foundation for everything else.

  T-6 weeks    Build Reddit scraper (PRAW). Scrape top 1000 posts per
               subreddit, deduplicated.

  T-6 weeks    Build blog RSS scraper. Manually curate 30-50 seed blogs
               per target region.

  T-5 weeks    Build batch LLM extraction pipeline. Process corpus
               against controlled vibe vocab.

  T-4 weeks    Build local platform scraper (Tabelog, Naver). Aggregate
               scores only for now.

  T-4 weeks    Build cross-reference confidence scorer. Merge signals
               into ActivityNode quality_signals.

  T-3 weeks    Build compressed LLM ranker (Section 2.3). Validate cost
               model against corpus.

  T-2 weeks    Build interaction logger (Section 4.5). This must be in
               production before first user.

  T-2 weeks    Set up shadow mode infrastructure (Section 4.3). BPR
               shadow starts from day 1.

  T-0 weeks    Launch. LLM ranker live. All interactions logged. BPR
               training queue accumulating.

  Month 3-4    Train first BPR model. Run shadow mode for 4 weeks. Apply
               promotion gate.

  Month 5      BPR promoted for warm users. Train vibe tagger MLP on
               accumulated tags.

  Month 6-8    Train two-tower. Shadow against BPR. Item embeddings
               pre-computed nightly.

  Month 9      Two-tower promoted. LightGCN training begins (requires 10K
               edge threshold).
  -----------------------------------------------------------------------

The system is designed so that each phase is usable in production
without the next. Month 0 with no ML is not a degraded state --- it\'s
an intentional, honest baseline that improves continuously as data
arrives.
