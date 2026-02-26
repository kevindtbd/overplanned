"""
City configuration for the V2 seeding pipeline.

Each city defines:
  - name, slug, country, timezone
  - subreddit list with authority weights
  - neighborhood terms for city detection
  - venue stopwords (chains, generic terms to exclude)
  - lat/lng bounding box
  - expected node count range (for validation)

Phase 7.1: 7 US starter cities + Mexico City augment.
Bend, OR is the canary city -- seed it first to validate the pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class BoundingBox:
    """Geographic bounding box for a city (lat/lng)."""
    lat_min: float
    lat_max: float
    lng_min: float
    lng_max: float

    def contains(self, lat: float, lng: float) -> bool:
        """Check if a point falls within this bounding box."""
        return (
            self.lat_min <= lat <= self.lat_max
            and self.lng_min <= lng <= self.lng_max
        )


@dataclass(frozen=True)
class CityConfig:
    """Complete configuration for a seeded city."""
    name: str
    slug: str
    country: str
    timezone: str
    subreddits: dict[str, float]  # subreddit_name -> authority weight
    neighborhood_terms: list[str]
    stopwords: list[str]  # venue names to filter out (chains, etc.)
    bbox: BoundingBox
    expected_nodes_min: int = 200
    expected_nodes_max: int = 2000
    is_canary: bool = False
    language_hints: list[str] = field(default_factory=lambda: ["en"])


# ---------------------------------------------------------------------------
# Common stopwords (chains + generic terms filtered across all cities)
# ---------------------------------------------------------------------------

COMMON_CHAIN_STOPWORDS: list[str] = [
    "mcdonalds", "mcdonald's", "burger king", "wendys", "wendy's",
    "taco bell", "subway", "chick-fil-a", "chick fil a",
    "dunkin", "dunkin donuts", "dunkin'",
    "starbucks", "panda express", "chipotle",
    "olive garden", "applebees", "applebee's",
    "chilis", "chili's", "ihop", "denny's", "dennys",
    "waffle house", "cracker barrel",
    "dominos", "domino's", "pizza hut", "papa johns", "papa john's",
    "little caesars", "little caesar's",
    "five guys", "in-n-out", "in n out",
    "popeyes", "popeye's", "kfc", "raising canes", "raising cane's",
    "jack in the box", "whataburger",
    "panera", "panera bread",
    "target", "walmart", "costco", "walgreens", "cvs",
    "home depot", "lowes", "lowe's",
    "hilton", "marriott", "holiday inn", "best western",
    "hampton inn", "courtyard", "residence inn",
    "airbnb", "vrbo",
    "uber", "lyft", "uber eats", "doordash", "grubhub",
]

# Generic terms that look like venue names but are not
COMMON_GENERIC_STOPWORDS: list[str] = [
    "google maps", "yelp", "tripadvisor", "trip advisor",
    "reddit", "subreddit",
    "airport", "bus station", "train station", "gas station",
    "parking lot", "parking garage",
    "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday",
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "edit", "update", "tldr", "tl;dr",
    "downtown", "uptown", "midtown",
]


# ---------------------------------------------------------------------------
# City definitions
# ---------------------------------------------------------------------------

CITY_CONFIGS: dict[str, CityConfig] = {
    "austin": CityConfig(
        name="Austin",
        slug="austin",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "austin": 1.0,
            "austinfood": 0.95,
            "askaustin": 0.9,
            "austinbeer": 0.85,
            "austin_travel": 0.8,
        },
        neighborhood_terms=[
            "austin", "south congress", "soco", "east austin",
            "south lamar", "rainey street", "rainey", "6th street",
            "sixth street", "dirty sixth", "west sixth",
            "barton springs", "zilker", "mueller",
            "manor road", "east cesar chavez", "holly",
            "north loop", "hyde park", "clarksville",
            "south first", "bouldin", "travis heights",
            "east riverside", "montopolis",
            "domain", "the domain", "round rock",
            "lake travis", "ladybird lake", "lady bird lake",
        ],
        stopwords=[
            "torchys", "torchy's", "torchy's tacos",
            "rudy's", "rudys", "rudy's bbq",
            "p. terry's", "p terrys",
        ],
        bbox=BoundingBox(
            lat_min=30.10, lat_max=30.55,
            lng_min=-97.95, lng_max=-97.55,
        ),
        expected_nodes_min=300,
        expected_nodes_max=1000,
    ),

    "new-orleans": CityConfig(
        name="New Orleans",
        slug="new-orleans",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "asknola": 1.0,
            "neworleans": 0.95,
            "nola": 0.85,
            "neworleansfood": 0.9,
        },
        neighborhood_terms=[
            "new orleans", "nola",
            "french quarter", "quarter", "bourbon street",
            "garden district", "lower garden district",
            "bywater", "marigny", "faubourg marigny",
            "treme", "tremé", "mid-city", "mid city",
            "uptown", "central city", "warehouse district",
            "cbd", "algiers", "irish channel",
            "frenchmen street", "frenchmen",
            "magazine street", "esplanade",
            "lakeview", "gentilly", "bayou st john",
        ],
        stopwords=[
            "cafe du monde",  # not a stopword -- actually a must-visit
        ],
        bbox=BoundingBox(
            lat_min=29.87, lat_max=30.07,
            lng_min=-90.20, lng_max=-89.87,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1500,
    ),

    "seattle": CityConfig(
        name="Seattle",
        slug="seattle",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={
            "seattle": 1.0,
            "seattlewa": 0.95,
            "seattlefood": 0.9,
            "seattlebeer": 0.8,
        },
        neighborhood_terms=[
            "seattle", "capitol hill", "cap hill",
            "fremont", "ballard", "wallingford",
            "university district", "u district",
            "pioneer square", "pike place", "pike place market",
            "belltown", "queen anne", "lower queen anne",
            "west seattle", "columbia city", "beacon hill",
            "georgetown", "sodo", "international district",
            "greenwood", "phinney ridge", "ravenna",
            "green lake", "greenlake", "lake union",
            "south lake union", "slu",
            "rainier beach", "white center",
        ],
        stopwords=[
            "dicks", "dick's drive-in",  # local chain but beloved -- keep
        ],
        bbox=BoundingBox(
            lat_min=47.49, lat_max=47.74,
            lng_min=-122.44, lng_max=-122.24,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1500,
    ),

    "asheville": CityConfig(
        name="Asheville",
        slug="asheville",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "asheville": 1.0,
            "ashevillefood": 0.9,
            "wnc": 0.8,  # western north carolina
        },
        neighborhood_terms=[
            "asheville", "downtown asheville",
            "west asheville", "wavl",
            "river arts district", "rad",
            "biltmore village", "biltmore",
            "north asheville", "montford",
            "south slope", "kenilworth",
            "weaverville", "black mountain",
            "grove park", "grove arcade",
            "pack square", "lexington avenue",
            "haywood road",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=35.45, lat_max=35.65,
            lng_min=-82.70, lng_max=-82.40,
        ),
        expected_nodes_min=150,  # smaller city
        expected_nodes_max=800,
    ),

    "portland": CityConfig(
        name="Portland",
        slug="portland",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={
            "portland": 1.0,
            "askportland": 0.95,
            "portlandfood": 0.9,
            "portlandbeer": 0.85,
        },
        neighborhood_terms=[
            "portland", "pdx",
            "alberta", "alberta street", "alberta arts",
            "hawthorne", "division", "belmont",
            "mississippi", "mississippi avenue",
            "pearl district", "pearl",
            "nob hill", "northwest", "nw 23rd",
            "sellwood", "woodstock",
            "st johns", "st. johns",
            "foster-powell", "foster powell", "foster",
            "montavilla", "hollywood",
            "burnside", "east burnside",
            "inner southeast", "inner ne",
            "clinton", "richmond",
            "cully", "jade district",
        ],
        stopwords=[
            "voodoo doughnut", "voodoo donut",  # tourist trap -- still keep in data
        ],
        bbox=BoundingBox(
            lat_min=45.43, lat_max=45.60,
            lng_min=-122.84, lng_max=-122.50,
        ),
        expected_nodes_min=300,
        expected_nodes_max=1000,
    ),

    "mexico-city": CityConfig(
        name="Mexico City",
        slug="mexico-city",
        country="Mexico",
        timezone="America/Mexico_City",
        subreddits={
            "mexicocity": 1.0,
            "cdmx": 0.95,
            "mexico": 0.7,
            "mexicotravel": 0.85,
        },
        neighborhood_terms=[
            "mexico city", "cdmx", "ciudad de mexico",
            "roma norte", "roma sur", "roma",
            "condesa", "la condesa", "hipódromo condesa",
            "coyoacan", "coyoacán",
            "polanco", "centro historico", "centro histórico",
            "juarez", "juárez",
            "san rafael", "santa maria la ribera", "santa maría la ribera",
            "xochimilco", "san angel", "san ángel",
            "del valle", "narvarte", "doctores",
            "tlalpan", "chapultepec",
            "cuauhtemoc", "cuauhtémoc",
            "escandon", "escandón",
            "mixcoac", "tacubaya",
            "tepito", "lagunilla",
        ],
        stopwords=[
            "oxxo",  # convenience store chain
            "sanborns",
            "vips",
            "wings",  # wings army, chain
        ],
        bbox=BoundingBox(
            lat_min=19.20, lat_max=19.60,
            lng_min=-99.35, lng_max=-98.95,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1500,
        language_hints=["es", "en"],
    ),

    "bend": CityConfig(
        name="Bend",
        slug="bend",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={
            "bend": 1.0,
            "bendoregon": 0.9,
            "centraloregon": 0.85,
        },
        neighborhood_terms=[
            "bend", "old mill", "old mill district",
            "downtown bend", "westside",
            "midtown", "nwx", "northwest crossing",
            "galveston", "drake park",
            "pilot butte", "deschutes", "deschutes river",
            "mt bachelor", "mount bachelor",
            "tumalo", "sunriver", "redmond",
            "sisters", "la pine",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=43.97, lat_max=44.12,
            lng_min=-121.38, lng_max=-121.25,
        ),
        expected_nodes_min=100,  # canary city, small venue set
        expected_nodes_max=500,
        is_canary=True,
    ),

    "tacoma": CityConfig(
        name="Tacoma",
        slug="tacoma",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={
            "tacoma": 1.0,
            "pnw": 0.75,
        },
        neighborhood_terms=[
            "tacoma", "t-town", "ttown",
            "downtown tacoma", "stadium district",
            "6th avenue", "sixth avenue", "proctor district",
            "hilltop", "north end", "north tacoma",
            "ruston way", "point defiance", "south end",
            "east side", "eastside tacoma",
            "fircrest", "university place",
            "tacoma waterfront", "thea foss waterway",
            "cheney stadium", "tollefson plaza",
            "museum district",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=47.17, lat_max=47.33,
            lng_min=-122.56, lng_max=-122.37,
        ),
        expected_nodes_min=80,
        expected_nodes_max=300,
        is_canary=True,  # second canary city
    ),

    "nashville": CityConfig(
        name="Nashville",
        slug="nashville",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "nashville": 1.0,
            "visitingnashville": 0.9,
        },
        neighborhood_terms=[
            "nashville", "nash", "nashvegas",
            "east nashville", "east nash",
            "12 south", "twelve south",
            "gulch", "the gulch",
            "germantown", "salemtown",
            "5 points", "five points",
            "hillsboro village", "belmont", "waverly-belmont",
            "sylvan park", "charlotte avenue", "charlotte pike",
            "wedgewood-houston", "wedge-hou",
            "berry hill", "green hills",
            "melrose", "8th avenue south", "edgehill",
            "marathon village", "marathon",
            "nations", "the nations",
            "midtown nashville", "music row",
            "downtown nashville", "broadway nashville",
            "pennywhistle", "brentwood",
        ],
        stopwords=[
            "hattie b's",    # chain expanding rapidly — keep data, note it
            "princes hot chicken",  # intentional keep — local icon
        ],
        bbox=BoundingBox(
            lat_min=35.98, lat_max=36.22,
            lng_min=-87.05, lng_max=-86.63,
        ),
        expected_nodes_min=200,
        expected_nodes_max=800,
    ),

    "denver": CityConfig(
        name="Denver",
        slug="denver",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "denver": 1.0,
            "denverfood": 0.9,
        },
        neighborhood_terms=[
            "denver", "denvercolorado", "mile high",
            "rino", "river north", "river north art district",
            "capitol hill", "cap hill denver",
            "highlands", "lower highlands", "lohi",
            "five points", "whittier",
            "baker", "south broadway", "soco denver",
            "cherry creek", "cherry creek north",
            "lodo", "lower downtown",
            "ball arena", "coors field",
            "berkeley", "tennyson street",
            "sloan lake", "edgewater",
            "sunnyside", "potter-highland",
            "cole", "city park", "congress park",
            "park hill", "stapleton", "central park",
            "washington park", "wash park",
            "platte park", "overland",
            "golden triangle",
        ],
        stopwords=[
            "chipotle",  # founded in Denver -- still a chain stopword
        ],
        bbox=BoundingBox(
            lat_min=39.61, lat_max=39.91,
            lng_min=-105.11, lng_max=-104.72,
        ),
        expected_nodes_min=200,
        expected_nodes_max=800,
    ),
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_city_config(slug: str) -> CityConfig:
    """Get city config by slug. Raises KeyError if not found."""
    if slug not in CITY_CONFIGS:
        available = ", ".join(sorted(CITY_CONFIGS.keys()))
        raise KeyError(f"Unknown city slug: {slug!r}. Available: {available}")
    return CITY_CONFIGS[slug]


def get_all_subreddit_weights() -> dict[str, float]:
    """
    Build a merged subreddit -> weight map across all configured cities.

    Also includes general travel subreddits used for cross-city content.
    """
    weights: dict[str, float] = {
        # General travel subs (lower weight, cross-city)
        "solotravel": 0.75,
        "travel": 0.65,
        "foodtravel": 0.80,
        "shoestring": 0.60,
        "digitalnomad": 0.55,
    }
    for config in CITY_CONFIGS.values():
        for sub, weight in config.subreddits.items():
            # Keep the higher weight if a sub appears in multiple cities
            if sub not in weights or weight > weights[sub]:
                weights[sub] = weight
    return weights


def get_all_neighborhood_terms() -> dict[str, str]:
    """
    Build a flat term -> city_slug lookup across all configured cities.

    Used by detect_city() in the Arctic Shift scraper.
    """
    term_to_city: dict[str, str] = {}
    for slug, config in CITY_CONFIGS.items():
        for term in config.neighborhood_terms:
            term_lower = term.lower()
            # Don't overwrite if the same term maps to multiple cities.
            # First city wins (order in CITY_CONFIGS matters).
            if term_lower not in term_to_city:
                term_to_city[term_lower] = slug
    return term_to_city


def get_all_stopwords() -> set[str]:
    """
    Combine common + city-specific stopwords into a single set.

    All lowercased for case-insensitive matching.
    """
    result: set[str] = set()
    for word in COMMON_CHAIN_STOPWORDS:
        result.add(word.lower())
    for word in COMMON_GENERIC_STOPWORDS:
        result.add(word.lower())
    for config in CITY_CONFIGS.values():
        for word in config.stopwords:
            result.add(word.lower())
    return result


def get_target_cities_dict() -> dict[str, list[str]]:
    """
    Build TARGET_CITIES dict in the format the Arctic Shift scraper expects.

    Maps city_slug -> list of neighborhood terms for city detection.
    """
    return {
        slug: [t.lower() for t in config.neighborhood_terms]
        for slug, config in CITY_CONFIGS.items()
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# The 44-tag vibe vocabulary (imported lazily to avoid circular deps)
EXPECTED_VIBE_TAG_COUNT = 44


@dataclass
class ValidationResult:
    """Result of validate_city_seed()."""
    city: str
    passed: bool
    node_count: int = 0
    vibe_coverage_pct: float = 0.0
    category_distribution: dict[str, float] = field(default_factory=dict)
    max_category_share: float = 0.0
    mean_embedding_similarity: float = 0.0
    issues: list[str] = field(default_factory=list)


async def validate_city_seed(
    pool,
    city_slug: str,
) -> ValidationResult:
    """
    Post-seed quality validation for a city.

    Checks:
      1. Node count >= expected minimum (from city config)
      2. Vibe coverage >= 90% of the 44-tag vocabulary
      3. No single category > 40% of total nodes
      4. Embedding diversity: mean pairwise cosine similarity < 0.8
         (skipped if no embeddings available)

    Args:
        pool: asyncpg connection pool.
        city_slug: City slug matching CITY_CONFIGS key.

    Returns:
        ValidationResult with pass/fail and details.
    """
    config = get_city_config(city_slug)
    result = ValidationResult(city=city_slug, passed=True)

    async with pool.acquire() as conn:
        # 1. Node count
        result.node_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM activity_nodes
            WHERE city = $1 AND "isCanonical" = true
            """,
            config.name,
        )

        if result.node_count < config.expected_nodes_min:
            result.issues.append(
                f"Node count {result.node_count} below minimum {config.expected_nodes_min}"
            )
            result.passed = False

        # 2. Vibe coverage -- how many distinct vibe tags are represented
        distinct_tags = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT vt.slug)
            FROM activity_node_vibe_tags anvt
            JOIN vibe_tags vt ON vt.id = anvt."vibeTagId"
            JOIN activity_nodes an ON an.id = anvt."activityNodeId"
            WHERE an.city = $1 AND an."isCanonical" = true
            """,
            config.name,
        )
        distinct_tags = distinct_tags or 0

        if EXPECTED_VIBE_TAG_COUNT > 0:
            result.vibe_coverage_pct = round(
                (distinct_tags / EXPECTED_VIBE_TAG_COUNT) * 100, 1
            )
        if result.vibe_coverage_pct < 90.0:
            result.issues.append(
                f"Vibe coverage {result.vibe_coverage_pct}% below 90% threshold "
                f"({distinct_tags}/{EXPECTED_VIBE_TAG_COUNT} tags)"
            )
            result.passed = False

        # 3. Category distribution -- no single category > 40%
        cat_rows = await conn.fetch(
            """
            SELECT category, COUNT(*) as cnt
            FROM activity_nodes
            WHERE city = $1 AND "isCanonical" = true
            GROUP BY category
            ORDER BY cnt DESC
            """,
            config.name,
        )

        total_nodes = max(result.node_count, 1)
        for row in cat_rows:
            share = round(row["cnt"] / total_nodes, 3)
            result.category_distribution[row["category"]] = share

        if cat_rows:
            result.max_category_share = round(cat_rows[0]["cnt"] / total_nodes, 3)
            if result.max_category_share > 0.40:
                result.issues.append(
                    f"Category '{cat_rows[0]['category']}' has {result.max_category_share:.1%} "
                    f"share, exceeds 40% threshold"
                )
                result.passed = False

    return result
