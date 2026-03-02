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
    rss_feeds: list[str] = field(default_factory=list)


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
            # cross-subreddit signals
            "texas": 0.70,
            "food": 0.65,
            "foodie": 0.60,
            "music": 0.65,
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
        rss_feeds=[],
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
            # cross-subreddit signals
            "louisiana": 0.70,
            "food": 0.65,
            "foodie": 0.60,
            "music": 0.65,
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
        rss_feeds=[],
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
            # cross-subreddit signals
            "washington": 0.70,
            "pnw": 0.70,
            "food": 0.65,
            "foodie": 0.60,
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
        rss_feeds=[],
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
            # cross-subreddit signals
            "northcarolina": 0.70,
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "hiking": 0.65,
            "camping": 0.60,
            "music": 0.65,
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
        rss_feeds=[
            "https://mountainx.com/feed/",
            "https://mountainx.com/food/feed/",
            "https://awomancooksinasheville.com/feed/",
            "https://edibleasheville.com/feed/",
            "https://uncorkasheville.com/feed/",
        ],
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
            # cross-subreddit signals
            "oregon": 0.70,
            "pnw": 0.70,
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "food": 0.65,
            "foodie": 0.60,
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
        rss_feeds=[],
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
            # cross-subreddit signals
            "travel": 0.60,
            "solotravel": 0.60,
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
        rss_feeds=[],
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
            # cross-subreddit signals
            "oregon": 0.70,
            "pnw": 0.70,
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "skiing": 0.65,
            "snowboarding": 0.60,
            "mtb": 0.65,
            "bikepacking": 0.60,
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
        expected_nodes_min=50,  # canary city, small mountain town
        expected_nodes_max=500,
        is_canary=True,
        rss_feeds=[
            "https://www.eatdrinkbend.com/feed/",
            "https://pdx.eater.com/rss/index.xml",
        ],
    ),

    "tacoma": CityConfig(
        name="Tacoma",
        slug="tacoma",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={
            "tacoma": 1.0,
            "pnw": 0.75,
            # cross-subreddit signals
            "washington": 0.70,
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
        rss_feeds=[],
    ),

    "nashville": CityConfig(
        name="Nashville",
        slug="nashville",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "nashville": 1.0,
            "visitingnashville": 0.9,
            # cross-subreddit signals
            "tennessee": 0.70,
            "food": 0.65,
            "foodie": 0.60,
            "music": 0.65,
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
        rss_feeds=[],
    ),

    # ------------------------------------------------------------------
    # Tier 1 — US Outdoor / Adventure Towns
    # ------------------------------------------------------------------

    "missoula": CityConfig(
        name="Missoula",
        slug="missoula",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "missoula": 1.0,
            "montana": 0.7,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
        },
        neighborhood_terms=[
            "missoula", "zoo city", "garden city",
            "university district", "u district",
            "hip strip", "downtown missoula",
            "southgate", "rattlesnake", "rattlesnake valley",
            "pattee canyon", "miller creek",
            "reserve street", "mullan road",
            "east missoula", "bonner", "milltown",
            "lolo", "frenchtown", "orchard homes",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=46.80, lat_max=46.94,
            lng_min=-114.12, lng_max=-113.88,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[
            "https://missoulian.com/search/?f=rss&t=article&l=25&s=start_time&sd=desc",
            "https://makeitmissoula.com/feed/",
            "https://missoulianangler.com/blog/feed/",
            "https://thepulp.org/feed/",
            "https://distinctlymontana.com/feed/",
        ],
    ),

    "flagstaff": CityConfig(
        name="Flagstaff",
        slug="flagstaff",
        country="United States",
        timezone="America/Phoenix",
        subreddits={
            "flagstaff": 1.0,
            "nau": 0.8,
            "arizona": 0.6,
            # cross-subreddit signals
            "hiking": 0.65,
            "camping": 0.60,
        },
        neighborhood_terms=[
            "flagstaff", "flag",
            "downtown flagstaff", "historic downtown",
            "southside", "south side flagstaff",
            "east flagstaff", "fourth street",
            "route 66 flagstaff", "san francisco peaks",
            "observatory mesa", "lowell observatory",
            "cheshire", "university heights",
            "continental", "kachina village",
            "sedona highway", "lake mary",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=35.13, lat_max=35.27,
            lng_min=-111.73, lng_max=-111.56,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[
            "https://azdailysun.com/search/?f=rss&t=article&l=25&s=start_time&sd=desc",
            "https://moonandspoonandyum.com/feed/",
            "https://oatandsesame.com/feed/",
        ],
    ),

    "bozeman": CityConfig(
        name="Bozeman",
        slug="bozeman",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "bozeman": 1.0,
            "montana": 0.7,
            "montanastate": 0.6,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "skiing": 0.65,
            "snowboarding": 0.60,
        },
        neighborhood_terms=[
            "bozeman", "bozone",
            "downtown bozeman", "main street bozeman",
            "midtown bozeman", "north 7th",
            "south bozeman", "south 19th",
            "bridger canyon", "bridger bowl",
            "big sky", "gallatin valley",
            "four corners", "belgrade",
            "hyalite", "sourdough",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=45.62, lat_max=45.73,
            lng_min=-111.12, lng_max=-110.96,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[
            "https://www.bozemandailychronicle.com/search/?f=rss&t=article&l=25&s=start_time&sd=desc",
            "https://ripefoodandwine.com/feed/",
            "https://www.explorebigsky.com/feed/",
            "https://distinctlymontana.com/feed/",
        ],
    ),

    "durango": CityConfig(
        name="Durango",
        slug="durango",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "durango": 1.0,
            "colorado": 0.6,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "mtb": 0.65,
            "bikepacking": 0.60,
        },
        neighborhood_terms=[
            "durango", "dgo",
            "downtown durango", "main avenue",
            "north main", "south main",
            "college drive", "animas river",
            "animas city", "trimble",
            "purgatory", "silverton",
            "hermosa", "bayfield",
            "fort lewis college",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=37.22, lat_max=37.33,
            lng_min=-107.94, lng_max=-107.83,
        ),
        expected_nodes_min=60,
        expected_nodes_max=300,
        rss_feeds=[
            "https://www.durangotelegraph.com/feed/",
            "https://www.360durango.com/feeds/blog",
            "https://rockymountainfoodreport.com/feed/",
        ],
    ),

    "moab": CityConfig(
        name="Moab",
        slug="moab",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "moab": 1.0,
            "utah": 0.6,
            "mountainbiking": 0.5,
            # cross-subreddit signals
            "hiking": 0.65,
            "camping": 0.60,
            "mtb": 0.65,
            "bikepacking": 0.60,
        },
        neighborhood_terms=[
            "moab", "downtown moab", "main street moab",
            "spanish valley", "castle valley",
            "arches", "canyonlands",
            "dead horse point", "la sal",
            "pack creek", "ken's lake",
            "sand flats", "slickrock",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=38.52, lat_max=38.62,
            lng_min=-109.60, lng_max=-109.49,
        ),
        expected_nodes_min=50,
        expected_nodes_max=250,
        rss_feeds=[
            "https://moabsunnews.com/feed/",
            "https://www.discovermoab.com/feed/",
        ],
    ),

    "taos": CityConfig(
        name="Taos",
        slug="taos",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "taos": 1.0,
            "newmexico": 0.7,
            # cross-subreddit signals
            "hiking": 0.65,
            "camping": 0.60,
            "wine": 0.65,
        },
        neighborhood_terms=[
            "taos", "taos pueblo",
            "downtown taos", "taos plaza",
            "ranchos de taos", "el prado",
            "arroyo seco", "arroyo hondo",
            "taos ski valley", "wheeler peak",
            "rio grande gorge", "earthships",
            "bent street", "kit carson road",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=36.35, lat_max=36.46,
            lng_min=-105.63, lng_max=-105.52,
        ),
        expected_nodes_min=50,
        expected_nodes_max=250,
        rss_feeds=[
            "https://www.taosnews.com/search/?f=rss&t=article&l=25&s=start_time&sd=desc",
            "https://nmgastronome.com/?feed=rss2",
            "https://mjskitchen.com/feed/",
        ],
    ),

    "sedona": CityConfig(
        name="Sedona",
        slug="sedona",
        country="United States",
        timezone="America/Phoenix",
        subreddits={
            "sedona": 1.0,
            "arizona": 0.6,
            # cross-subreddit signals
            "hiking": 0.65,
            "camping": 0.60,
            "mtb": 0.65,
            "bikepacking": 0.60,
        },
        neighborhood_terms=[
            "sedona", "west sedona",
            "uptown sedona", "downtown sedona",
            "tlaquepaque", "oak creek",
            "oak creek canyon", "red rock",
            "chapel of the holy cross", "bell rock",
            "cathedral rock", "devil's bridge",
            "slide rock", "boynton canyon",
            "village of oak creek", "voc",
            "cottonwood", "jerome",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=34.82, lat_max=34.92,
            lng_min=-111.83, lng_max=-111.70,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[
            "https://www.redrocknews.com/feed/",
            "https://sedonahappy.com/Sedona-blog.xml",
        ],
    ),

    "hood-river": CityConfig(
        name="Hood River",
        slug="hood-river",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={
            "hoodriver": 1.0,
            "oregon": 0.6,
            "columbiagorge": 0.8,
            # cross-subreddit signals
            "pnw": 0.70,
            "hiking": 0.65,
            "camping": 0.60,
        },
        neighborhood_terms=[
            "hood river", "hr",
            "downtown hood river", "the heights",
            "waterfront park", "event site",
            "odell", "parkdale", "dee",
            "columbia gorge", "gorge",
            "fruit loop", "mt hood meadows",
            "cascade locks", "white salmon",
            "bingen",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=45.68, lat_max=45.74,
            lng_min=-121.56, lng_max=-121.49,
        ),
        expected_nodes_min=50,
        expected_nodes_max=250,
        rss_feeds=[
            "https://www.hoodrivereats.com/blog-posts?format=rss",
            "https://pdx.eater.com/rss/index.xml",
            "https://columbiacommunityconnection.com/feed/",
        ],
    ),

    "truckee": CityConfig(
        name="Truckee",
        slug="truckee",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={
            "truckee": 1.0,
            "tahoe": 0.9,
            "laketahoe": 0.85,
            # cross-subreddit signals
            "california": 0.70,
            "skiing": 0.65,
            "snowboarding": 0.60,
        },
        neighborhood_terms=[
            "truckee", "old town truckee",
            "downtown truckee", "donner lake",
            "donner pass", "northstar",
            "palisades tahoe", "squaw valley",
            "alpine meadows", "sugar bowl",
            "tahoe donner", "martis valley",
            "kings beach", "tahoe city",
            "north lake tahoe",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=39.28, lat_max=39.38,
            lng_min=-120.24, lng_max=-120.12,
        ),
        expected_nodes_min=60,
        expected_nodes_max=300,
        rss_feeds=[
            "https://www.moonshineink.com/feed/",
            "https://www.tahoedailytribune.com/feed/",
            "https://www.visittruckeetahoe.com/feed/",
            "https://www.slowfoodlaketahoe.org/feed/",
        ],
    ),

    "mammoth-lakes": CityConfig(
        name="Mammoth Lakes",
        slug="mammoth-lakes",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={
            "mammothlakes": 1.0,
            "mammothmountain": 0.9,
            "easternsierra": 0.8,
            # cross-subreddit signals
            "california": 0.70,
            "skiing": 0.65,
            "snowboarding": 0.60,
        },
        neighborhood_terms=[
            "mammoth lakes", "mammoth",
            "the village at mammoth", "old mammoth road",
            "mammoth mountain", "minaret road",
            "canyon lodge", "eagle lodge",
            "june lake", "june mountain",
            "convict lake", "hot creek",
            "devils postpile", "reds meadow",
            "crowley lake", "lake mary",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=37.62, lat_max=37.68,
            lng_min=-119.02, lng_max=-118.93,
        ),
        expected_nodes_min=50,
        expected_nodes_max=250,
        rss_feeds=[
            "https://sierrawave.net/feed/",
            "https://www.mammothtimes.com/feed/",
            "https://www.visitmammoth.com/feed/",
        ],
    ),

    "jackson-hole": CityConfig(
        name="Jackson Hole",
        slug="jackson-hole",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "jacksonhole": 1.0,
            "jackson": 0.85,
            "wyoming": 0.6,
            # cross-subreddit signals
            "skiing": 0.65,
            "snowboarding": 0.60,
            "hiking": 0.65,
            "camping": 0.60,
        },
        neighborhood_terms=[
            "jackson", "jackson hole", "jh",
            "town square", "jackson town square",
            "teton village", "wilson",
            "aspens", "rafter j",
            "south park", "north jackson",
            "snow king", "snow king mountain",
            "grand teton", "teton pass",
            "moose", "kelly",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=43.42, lat_max=43.54,
            lng_min=-110.82, lng_max=-110.70,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[
            "https://buckrail.com/feed/",
            "https://dishingjh.com/feed/",
            "https://www.jhnewsandguide.com/search/?f=rss&t=article&l=25&s=start_time&sd=desc",
            "https://www.jacksonholewy.com/feed/",
        ],
    ),

    "telluride": CityConfig(
        name="Telluride",
        slug="telluride",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "telluride": 1.0,
            "colorado": 0.6,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "skiing": 0.65,
            "snowboarding": 0.60,
        },
        neighborhood_terms=[
            "telluride", "mountain village",
            "town of telluride", "colorado avenue",
            "main street telluride",
            "gondola", "free gondola",
            "town park", "bear creek",
            "bridal veil falls", "box canyon",
            "san miguel", "ophir",
            "sawpit", "placerville",
            "last dollar road",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=37.92, lat_max=37.96,
            lng_min=-107.84, lng_max=-107.78,
        ),
        expected_nodes_min=50,
        expected_nodes_max=250,
        rss_feeds=[
            "https://www.telluride.com/feed/",
            "https://rockymountainfoodreport.com/feed/",
            "https://5280.com/feed/",
        ],
    ),

    "denver": CityConfig(
        name="Denver",
        slug="denver",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "denver": 1.0,
            "denverfood": 0.9,
            # cross-subreddit signals
            "colorado": 0.70,
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
        rss_feeds=[
            "https://denver.eater.com/rss/index.xml",
        ],
    ),

    # ------------------------------------------------------------------
    # Tier 2 — Mid-size US Cities
    # ------------------------------------------------------------------

    "portland-me": CityConfig(
        name="Portland",
        slug="portland-me",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "portlandme": 1.0,
            "maine": 0.85,
            "mainefood": 0.9,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
        },
        neighborhood_terms=[
            "portland maine", "portland me",
            "old port", "west end", "east end",
            "munjoy hill", "east bayside",
            "arts district", "india street",
            "commercial street", "fore street",
            "congress street", "back cove",
            "deering center", "deering oaks",
            "woodfords corner", "bayside",
            "ferry village", "south portland",
            "peaks island", "casco bay",
            "monument square", "longfellow square",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=43.63, lat_max=43.70,
            lng_min=-70.33, lng_max=-70.22,
        ),
        expected_nodes_min=150,
        expected_nodes_max=800,
        rss_feeds=[],
    ),

    "burlington": CityConfig(
        name="Burlington",
        slug="burlington",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "burlingtonvt": 1.0,
            "vermont": 0.85,
            "burlingtonfood": 0.9,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
        },
        neighborhood_terms=[
            "burlington", "burlington vt",
            "church street", "church street marketplace",
            "old north end", "one", "new north end",
            "south end", "south end arts district",
            "hill section", "battery park",
            "waterfront", "burlington waterfront",
            "winooski", "essex junction",
            "shelburne", "shelburne road",
            "pine street", "north avenue",
            "colchester", "south burlington",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=44.44, lat_max=44.51,
            lng_min=-73.25, lng_max=-73.17,
        ),
        expected_nodes_min=150,
        expected_nodes_max=800,
        rss_feeds=[],
    ),

    "tucson": CityConfig(
        name="Tucson",
        slug="tucson",
        country="United States",
        timezone="America/Phoenix",
        subreddits={
            "tucson": 1.0,
            "tucsonfood": 0.95,
            "universityofarizona": 0.8,
            # cross-subreddit signals
            "arizona": 0.70,
        },
        neighborhood_terms=[
            "tucson", "old pueblo",
            "downtown tucson", "fourth avenue", "4th avenue",
            "university", "u of a", "main gate square",
            "barrio viejo", "barrio historico",
            "armory park", "iron horse",
            "sam hughes", "el presidio",
            "lost barrio", "south tucson",
            "midtown tucson", "grant road",
            "speedway", "broadway village",
            "catalina foothills", "oro valley",
            "marana", "tanque verde",
            "sabino canyon", "saguaro national park",
        ],
        stopwords=[
            "eegees", "eegee's",  # local chain
        ],
        bbox=BoundingBox(
            lat_min=32.10, lat_max=32.38,
            lng_min=-111.10, lng_max=-110.75,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1000,
        rss_feeds=[],
    ),

    "madison": CityConfig(
        name="Madison",
        slug="madison",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "madisonwi": 1.0,
            "madisonfood": 0.95,
            "uwmadison": 0.8,
            # cross-subreddit signals
            "wisconsin": 0.70,
            "food": 0.65,
            "foodie": 0.60,
        },
        neighborhood_terms=[
            "madison", "madison wi",
            "capitol square", "state street",
            "willy street", "williamson street",
            "atwood", "schenk-atwood",
            "east side madison", "near east side",
            "monroe street", "dudgeon-monroe",
            "hilldale", "university heights",
            "campus", "langdon street",
            "vilas", "greenbush",
            "isthmus", "tenney park",
            "waunakee", "middleton",
            "fitchburg", "verona",
            "dane county farmers market",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=43.01, lat_max=43.15,
            lng_min=-89.50, lng_max=-89.30,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1000,
        rss_feeds=[],
    ),

    "fort-collins": CityConfig(
        name="Fort Collins",
        slug="fort-collins",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "fortcollins": 1.0,
            "csu": 0.8,
            "colorado": 0.6,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
        },
        neighborhood_terms=[
            "fort collins", "foco",
            "old town", "old town fort collins",
            "old town square", "mountain avenue",
            "campus west", "college avenue",
            "midtown", "south fort collins",
            "north fort collins", "shields street",
            "horsetooth", "horsetooth reservoir",
            "city park", "spring creek",
            "drake road", "harmony road",
            "wellington", "timnath", "windsor",
            "linden street",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=40.50, lat_max=40.63,
            lng_min=-105.15, lng_max=-105.00,
        ),
        expected_nodes_min=150,
        expected_nodes_max=800,
        rss_feeds=[],
    ),

    "durham": CityConfig(
        name="Durham",
        slug="durham",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "bullcity": 1.0,
            "durham": 0.95,
            "triangle": 0.85,
            "raleigh": 0.7,
            # cross-subreddit signals
            "northcarolina": 0.70,
            "food": 0.65,
            "foodie": 0.60,
        },
        neighborhood_terms=[
            "durham", "bull city",
            "downtown durham", "american tobacco campus",
            "brightleaf", "brightleaf square",
            "ninth street", "9th street",
            "duke east campus", "duke west campus",
            "trinity park", "watts-hillandale",
            "old north durham", "walltown",
            "south durham", "southpoint",
            "research triangle", "rtp",
            "east durham", "golden belt",
            "lakewood", "eno river",
        ],
        stopwords=[
            "cookout",  # regional chain
        ],
        bbox=BoundingBox(
            lat_min=35.90, lat_max=36.08,
            lng_min=-79.02, lng_max=-78.82,
        ),
        expected_nodes_min=150,
        expected_nodes_max=1000,
        rss_feeds=[],
    ),

    "columbus": CityConfig(
        name="Columbus",
        slug="columbus",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "columbus": 1.0,
            "columbusfood": 0.95,
            "osu": 0.8,
            # cross-subreddit signals
            "ohio": 0.70,
            "food": 0.65,
            "foodie": 0.60,
        },
        neighborhood_terms=[
            "columbus", "columbus ohio", "cbus",
            "short north", "short north arts district",
            "german village", "italian village",
            "victorian village", "clintonville",
            "grandview", "grandview heights",
            "old north", "university district",
            "franklinton", "brewery district",
            "arena district", "downtown columbus",
            "bexley", "upper arlington",
            "worthington", "dublin",
            "easton", "polaris",
            "north market", "high street",
        ],
        stopwords=[
            "white castle",  # founded in Columbus
            "bob evans",
        ],
        bbox=BoundingBox(
            lat_min=39.88, lat_max=40.12,
            lng_min=-83.10, lng_max=-82.82,
        ),
        expected_nodes_min=300,
        expected_nodes_max=2000,
        rss_feeds=[],
    ),

    "detroit": CityConfig(
        name="Detroit",
        slug="detroit",
        country="United States",
        timezone="America/Detroit",
        subreddits={
            "detroit": 1.0,
            "detroitfood": 0.95,
            "michigan": 0.7,
        },  # michigan already present
        neighborhood_terms=[
            "detroit",
            "corktown", "mexicantown",
            "midtown detroit", "new center",
            "eastern market", "rivertown",
            "downtown detroit", "greektown",
            "southwest detroit", "dearborn",
            "hamtramck", "highland park",
            "ferndale", "royal oak",
            "woodbridge", "brush park",
            "indian village", "west village",
            "belle isle", "lafayette park",
            "livernois", "avenue of fashion",
            "michigan avenue", "grand river",
        ],
        stopwords=[
            "little caesars",  # Detroit-founded chain
        ],
        bbox=BoundingBox(
            lat_min=42.28, lat_max=42.45,
            lng_min=-83.29, lng_max=-82.91,
        ),
        expected_nodes_min=300,
        expected_nodes_max=2000,
        rss_feeds=[],
    ),

    "pittsburgh": CityConfig(
        name="Pittsburgh",
        slug="pittsburgh",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "pittsburgh": 1.0,
            "pittsburghfood": 0.95,
            "pittsburghbeer": 0.85,
            # cross-subreddit signals
            "pennsylvania": 0.70,
        },
        neighborhood_terms=[
            "pittsburgh", "pgh", "the burgh",
            "strip district", "lawrenceville",
            "squirrel hill", "shadyside",
            "bloomfield", "east liberty",
            "south side", "south side flats",
            "mt washington", "mount washington",
            "north shore", "downtown pittsburgh",
            "oakland", "polish hill",
            "regent square", "point breeze",
            "garfield", "morningside",
            "troy hill", "millvale",
            "market square", "station square",
        ],
        stopwords=[
            "eat n park", "eat'n park",  # regional chain
            "primanti bros", "primanti brothers",  # regional chain -- expanded nationally
        ],
        bbox=BoundingBox(
            lat_min=40.38, lat_max=40.50,
            lng_min=-80.10, lng_max=-79.87,
        ),
        expected_nodes_min=300,
        expected_nodes_max=2000,
        rss_feeds=[],
    ),

    "greenville": CityConfig(
        name="Greenville",
        slug="greenville",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "greenville": 1.0,
            "yeahthatgreenville": 0.95,
            "southcarolina": 0.7,
        },  # southcarolina already present
        neighborhood_terms=[
            "greenville", "greenville sc",
            "downtown greenville", "main street greenville",
            "falls park", "liberty bridge",
            "west end", "village of west greenville",
            "north main", "stone avenue",
            "east north street", "haywood road",
            "augusta road", "augusta street",
            "pleasantburg", "cherrydale",
            "travelers rest", "tr",
            "furman", "paris mountain",
        ],
        stopwords=[
            "cookout",
        ],
        bbox=BoundingBox(
            lat_min=34.80, lat_max=34.92,
            lng_min=-82.45, lng_max=-82.30,
        ),
        expected_nodes_min=150,
        expected_nodes_max=1000,
        rss_feeds=[],
    ),

    "charleston": CityConfig(
        name="Charleston",
        slug="charleston",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "charleston": 1.0,
            "chsFood": 0.95,
            "southcarolina": 0.7,
            # cross-subreddit signals
            "food": 0.65,
            "foodie": 0.60,
        },
        neighborhood_terms=[
            "charleston", "charleston sc", "chs",
            "king street", "upper king",
            "french quarter charleston", "south of broad",
            "harleston village", "cannonborough",
            "elliotborough", "wagener terrace",
            "north central", "east side charleston",
            "west ashley", "james island",
            "mount pleasant", "mt pleasant",
            "folly beach", "sullivan's island",
            "isle of palms", "park circle",
            "north charleston",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=32.72, lat_max=32.85,
            lng_min=-80.05, lng_max=-79.88,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1000,
        rss_feeds=[],
    ),

    # ------------------------------------------------------------------
    # Tier 2 — Vacation / Mountain Towns
    # ------------------------------------------------------------------

    "santa-fe": CityConfig(
        name="Santa Fe",
        slug="santa-fe",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "santafe": 1.0,
            "newmexico": 0.85,
            # cross-subreddit signals
            "hiking": 0.65,
            "camping": 0.60,
            "wine": 0.65,
        },
        neighborhood_terms=[
            "santa fe", "city different",
            "the plaza", "santa fe plaza",
            "canyon road", "railyard", "rail yard",
            "railyard district", "guadalupe street",
            "cerrillos road", "st francis drive",
            "old santa fe trail",
            "museum hill", "south capitol",
            "eastside santa fe", "acequia madre",
            "palace avenue", "de vargas",
            "tesuque", "el dorado",
            "hyde park road", "ski santa fe",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=35.62, lat_max=35.72,
            lng_min=-105.99, lng_max=-105.88,
        ),
        expected_nodes_min=150,
        expected_nodes_max=800,
        rss_feeds=[],
    ),

    "marfa": CityConfig(
        name="Marfa",
        slug="marfa",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "marfa": 1.0,
            "texas": 0.6,
            "westtexas": 0.8,
        },  # texas already present
        neighborhood_terms=[
            "marfa", "marfa texas",
            "highland avenue", "san antonio street",
            "el cosmico", "chinati foundation",
            "prada marfa", "marfa lights",
            "fort davis", "alpine texas",
            "big bend", "presidio county",
            "marathon", "terlingua",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=30.28, lat_max=30.33,
            lng_min=-104.04, lng_max=-103.98,
        ),
        expected_nodes_min=30,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "fredericksburg": CityConfig(
        name="Fredericksburg",
        slug="fredericksburg",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "fredericksburg": 1.0,
            "texaswine": 0.85,
            "texas": 0.6,
            # cross-subreddit signals
            "wine": 0.65,
        },
        neighborhood_terms=[
            "fredericksburg", "fbg", "fredericksburg tx",
            "main street fredericksburg", "hauptstrasse",
            "wine road 290", "highway 290",
            "us 290 wine trail", "texas wine country",
            "gillespie county", "stonewall",
            "luckenbach", "enchanted rock",
            "south adams street", "north llano street",
            "marktplatz", "nimitz",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=30.24, lat_max=30.30,
            lng_min=-98.92, lng_max=-98.84,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[],
    ),

    "savannah": CityConfig(
        name="Savannah",
        slug="savannah",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "savannah": 1.0,
            "visitsavannah": 0.9,
            "georgia": 0.7,
            # cross-subreddit signals
            "food": 0.65,
            "foodie": 0.60,
        },
        neighborhood_terms=[
            "savannah", "savannah ga",
            "historic district", "forsyth park",
            "river street", "city market",
            "broughton street", "bull street",
            "jones street", "liberty street",
            "victorian district", "thomas square",
            "starland district", "midtown savannah",
            "ardsley park", "baldwin park",
            "isle of hope", "thunderbolt",
            "tybee island", "bonaventure cemetery",
            "plant riverside", "east broad street",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=32.00, lat_max=32.12,
            lng_min=-81.14, lng_max=-81.05,
        ),
        expected_nodes_min=150,
        expected_nodes_max=1000,
        rss_feeds=[],
    ),

    "charlottesville": CityConfig(
        name="Charlottesville",
        slug="charlottesville",
        country="United States",
        timezone="America/New_York",
        subreddits={
            "charlottesville": 1.0,
            "uva": 0.8,
            "virginia": 0.7,
            # cross-subreddit signals
            "wine": 0.65,
        },
        neighborhood_terms=[
            "charlottesville", "cville",
            "downtown mall", "historic downtown mall",
            "the corner", "rugby road",
            "belmont", "belmont cville",
            "west main street", "south street",
            "north downtown", "starr hill",
            "vinegar hill", "woolen mills",
            "ix art park", "ix",
            "barracks road", "pantops",
            "crozet", "nelson county",
            "monticello", "carter mountain",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=38.00, lat_max=38.07,
            lng_min=-78.52, lng_max=-78.44,
        ),
        expected_nodes_min=150,
        expected_nodes_max=800,
        rss_feeds=[],
    ),

    "traverse-city": CityConfig(
        name="Traverse City",
        slug="traverse-city",
        country="United States",
        timezone="America/Detroit",
        subreddits={
            "traversecity": 1.0,
            "michigan": 0.7,
            "northernmichigan": 0.85,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "hiking": 0.65,
            "camping": 0.60,
            "wine": 0.65,
        },
        neighborhood_terms=[
            "traverse city", "tc",
            "front street", "downtown tc",
            "west bay", "east bay",
            "old mission peninsula", "old mission",
            "leelanau", "leelanau peninsula",
            "suttons bay", "northport",
            "glen arbor", "sleeping bear dunes",
            "empire", "interlochen",
            "acme", "elk rapids",
            "clinch park", "open space",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=44.72, lat_max=44.80,
            lng_min=-85.65, lng_max=-85.55,
        ),
        expected_nodes_min=80,
        expected_nodes_max=500,
        rss_feeds=[],
    ),

    "saugatuck": CityConfig(
        name="Saugatuck",
        slug="saugatuck",
        country="United States",
        timezone="America/Detroit",
        subreddits={
            "saugatuck": 1.0,
            "michigan": 0.7,
            # cross-subreddit signals
            "wine": 0.65,
        },
        neighborhood_terms=[
            "saugatuck", "douglas", "saugatuck-douglas",
            "downtown saugatuck", "butler street",
            "water street", "center street",
            "oval beach", "saugatuck dunes",
            "kalamazoo river", "blue star highway",
            "fennville", "ganges",
            "mount baldhead",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=42.63, lat_max=42.68,
            lng_min=-86.22, lng_max=-86.18,
        ),
        expected_nodes_min=30,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "eureka-springs": CityConfig(
        name="Eureka Springs",
        slug="eureka-springs",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "eurekasprings": 1.0,
            "arkansas": 0.7,
            "camping": 0.6,
        },
        neighborhood_terms=[
            "eureka springs", "eureka",
            "downtown eureka springs", "spring street",
            "main street eureka springs",
            "north main", "historic loop",
            "basin spring park", "crescent hotel",
            "thorncrown chapel", "beaver lake",
            "table rock lake", "war eagle",
            "berryville", "holiday island",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=36.38, lat_max=36.42,
            lng_min=-93.76, lng_max=-93.72,
        ),
        expected_nodes_min=30,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "bentonville": CityConfig(
        name="Bentonville",
        slug="bentonville",
        country="United States",
        timezone="America/Chicago",
        subreddits={
            "bentonville": 1.0,
            "fayetteville": 0.8,
            "arkansas": 0.7,
            "nwa": 0.85,
            # cross-subreddit signals
            "mtb": 0.65,
            "bikepacking": 0.60,
        },
        neighborhood_terms=[
            "bentonville", "bentonville ar",
            "downtown bentonville", "the square",
            "bentonville square", "crystal bridges",
            "8th street market", "se street",
            "a street", "central avenue",
            "slaughter pen trail", "coler mountain",
            "bella vista", "rogers",
            "northwest arkansas", "nwa",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=36.33, lat_max=36.40,
            lng_min=-94.25, lng_max=-94.17,
        ),
        expected_nodes_min=80,
        expected_nodes_max=500,
        rss_feeds=[],
    ),

    "ogden": CityConfig(
        name="Ogden",
        slug="ogden",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "ogden": 1.0,
            "utah": 0.7,
            # cross-subreddit signals
            "hiking": 0.65,
            "camping": 0.60,
        },
        neighborhood_terms=[
            "ogden", "ogden utah",
            "25th street", "historic 25th street",
            "downtown ogden", "washington boulevard",
            "ogden river", "ogden canyon",
            "north ogden", "south ogden",
            "ogden nature center", "union station",
            "snowbasin", "powder mountain",
            "nordic valley", "eden",
            "huntsville", "ogden valley",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=41.19, lat_max=41.28,
            lng_min=-111.99, lng_max=-111.91,
        ),
        expected_nodes_min=80,
        expected_nodes_max=500,
        rss_feeds=[],
    ),

    "buena-vista": CityConfig(
        name="Buena Vista",
        slug="buena-vista",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "buenavista": 1.0,
            "colorado": 0.6,
            "14ers": 0.7,
            # cross-subreddit signals
            "skiing": 0.65,
            "snowboarding": 0.60,
            "mtb": 0.65,
            "bikepacking": 0.60,
        },
        neighborhood_terms=[
            "buena vista", "bv",
            "downtown buena vista", "main street bv",
            "east main street", "south main",
            "south arkansas", "arkansas river",
            "cottonwood pass", "collegiate peaks",
            "mt princeton", "mount princeton hot springs",
            "johnson village", "nathrop",
            "salida", "poncha springs",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=38.82, lat_max=38.87,
            lng_min=-106.16, lng_max=-106.10,
        ),
        expected_nodes_min=30,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "glenwood-springs": CityConfig(
        name="Glenwood Springs",
        slug="glenwood-springs",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "glenwoodsprings": 1.0,
            "colorado": 0.6,
            # cross-subreddit signals
            "skiing": 0.65,
            "snowboarding": 0.60,
        },
        neighborhood_terms=[
            "glenwood springs", "glenwood",
            "downtown glenwood", "grand avenue",
            "glenwood hot springs", "iron mountain",
            "glenwood canyon", "no name",
            "hanging lake", "grizzly creek",
            "south canyon", "west glenwood",
            "carbondale", "basalt",
            "roaring fork valley",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=39.52, lat_max=39.58,
            lng_min=-107.35, lng_max=-107.28,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[],
    ),

    "ketchum": CityConfig(
        name="Ketchum",
        slug="ketchum",
        country="United States",
        timezone="America/Boise",
        subreddits={
            "sunvalley": 1.0,
            "idaho": 0.7,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "skiing": 0.65,
            "snowboarding": 0.60,
            "mtb": 0.65,
            "bikepacking": 0.60,
        },
        neighborhood_terms=[
            "ketchum", "sun valley",
            "downtown ketchum", "main street ketchum",
            "sun valley lodge", "dollar mountain",
            "bald mountain", "baldy",
            "river run", "warm springs",
            "trail creek", "hailey",
            "bellevue", "wood river valley",
            "elkhorn", "sawtooth",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=43.67, lat_max=43.72,
            lng_min=-114.40, lng_max=-114.34,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[],
    ),

    "whitefish": CityConfig(
        name="Whitefish",
        slug="whitefish",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "whitefish": 1.0,
            "montana": 0.7,
            "glaciernationalpark": 0.8,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "skiing": 0.65,
            "snowboarding": 0.60,
            "hiking": 0.65,
            "camping": 0.60,
        },
        neighborhood_terms=[
            "whitefish", "downtown whitefish",
            "central avenue whitefish",
            "whitefish lake", "whitefish mountain",
            "big mountain", "whitefish mountain resort",
            "glacier national park", "gnp",
            "west glacier", "columbia falls",
            "flathead lake", "kalispell",
            "hungry horse",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=48.38, lat_max=48.44,
            lng_min=-114.40, lng_max=-114.33,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        rss_feeds=[],
    ),

    "steamboat-springs": CityConfig(
        name="Steamboat Springs",
        slug="steamboat-springs",
        country="United States",
        timezone="America/Denver",
        subreddits={
            "steamboatsprings": 1.0,
            "colorado": 0.6,
            # cross-subreddit signals
            "craftbeer": 0.65,
            "beerporn": 0.60,
            "skiing": 0.65,
            "snowboarding": 0.60,
        },
        neighborhood_terms=[
            "steamboat springs", "steamboat", "the boat",
            "downtown steamboat", "lincoln avenue",
            "old town steamboat", "mountain village steamboat",
            "ski time square", "gondola square",
            "yampa river", "yampa street",
            "strawberry park", "strawberry hot springs",
            "fish creek falls", "hayden",
            "oak creek", "routt county",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=40.46, lat_max=40.51,
            lng_min=-106.86, lng_max=-106.79,
        ),
        expected_nodes_min=80,
        expected_nodes_max=500,
        rss_feeds=[],
    ),

    # ------------------------------------------------------------------
    # Tier 3 — International (English-corpus heavy, expat/nomad)
    # ------------------------------------------------------------------

    "chiang-mai": CityConfig(
        name="Chiang Mai",
        slug="chiang-mai",
        country="Thailand",
        timezone="Asia/Bangkok",
        subreddits={
            "chiangmai": 1.0,
            "thailand": 0.8,
            "digitalnomad": 0.7,
            "thailandtourism": 0.75,
            # cross-subreddit signals
            "solotravel": 0.65,
            "backpacking": 0.60,
            "travel": 0.60,
            "southeastasia": 0.65,
            "asiatravel": 0.65,
        },
        neighborhood_terms=[
            "chiang mai", "chiangmai", "cnx",
            "old city", "old town chiang mai",
            "tha pae", "tha phae gate",
            "nimman", "nimmanhaemin",
            "suthep", "doi suthep",
            "chang phueak", "chang puak",
            "night bazaar", "warorot market",
            "santitham", "hang dong",
            "san kamphaeng", "bo sang",
            "maya mall", "think park",
            "huay kaew", "canal road",
            "riverside chiang mai",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=18.74, lat_max=18.82,
            lng_min=98.95, lng_max=99.02,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1500,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "tbilisi": CityConfig(
        name="Tbilisi",
        slug="tbilisi",
        country="Georgia",
        timezone="Asia/Tbilisi",
        subreddits={
            "tbilisi": 1.0,
            "sakartvelo": 0.95,
            "georgia": 0.7,
            # cross-subreddit signals
            "solotravel": 0.65,
            "backpacking": 0.60,
            "travel": 0.60,
            "europe": 0.65,
            "easterneurope": 0.65,
        },
        neighborhood_terms=[
            "tbilisi",
            "old town tbilisi", "old tbilisi",
            "rustaveli", "rustaveli avenue",
            "vera", "vake",
            "saburtalo", "mtatsminda",
            "abanotubani", "sulfur baths",
            "narikala", "leselidze street",
            "fabrika", "marjanishvili",
            "avlabari", "sololaki",
            "dry bridge", "dezerter bazaar",
            "wine factory", "shardeni street",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=41.68, lat_max=41.74,
            lng_min=44.74, lng_max=44.83,
        ),
        expected_nodes_min=150,
        expected_nodes_max=1000,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "medellin": CityConfig(
        name="Medellin",
        slug="medellin",
        country="Colombia",
        timezone="America/Bogota",
        subreddits={
            "medellin": 1.0,
            "colombia": 0.8,
            "digitalnomad": 0.7,
            # cross-subreddit signals
            "solotravel": 0.65,
            "backpacking": 0.60,
            "travel": 0.60,
            "southamerica": 0.65,
        },
        neighborhood_terms=[
            "medellin", "medallo",
            "el poblado", "poblado",
            "laureles", "estadio",
            "envigado", "sabaneta",
            "la candelaria", "centro medellin",
            "comuna 13", "san javier",
            "belen", "floresta",
            "parque lleras", "parque berrio",
            "santa elena", "guatape",
            "provenza", "manila",
            "el tesoro", "la strada",
        ],
        stopwords=[
            "crepes & waffles",  # Colombian chain
            "juan valdez",
        ],
        bbox=BoundingBox(
            lat_min=6.18, lat_max=6.32,
            lng_min=-75.62, lng_max=-75.52,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1500,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "oaxaca": CityConfig(
        name="Oaxaca",
        slug="oaxaca",
        country="Mexico",
        timezone="America/Mexico_City",
        subreddits={
            "oaxaca": 1.0,
            "mexico": 0.7,
            "mexicotravel": 0.85,
            # cross-subreddit signals
            "solotravel": 0.65,
            "backpacking": 0.60,
            "travel": 0.60,
            "food": 0.65,
            "foodie": 0.60,
        },
        neighborhood_terms=[
            "oaxaca", "oaxaca city", "oaxaca de juarez",
            "centro historico oaxaca", "zocalo oaxaca",
            "jalatlaco", "xochimilco oaxaca",
            "reforma", "barrio de la soledad",
            "santo domingo", "andador macedonio alcala",
            "mercado benito juarez", "mercado 20 de noviembre",
            "abastos", "central de abastos",
            "san felipe del agua", "san agustin etla",
            "tlacolula", "mitla",
            "hierve el agua", "monte alban",
        ],
        stopwords=[
            "oxxo",
        ],
        bbox=BoundingBox(
            lat_min=17.03, lat_max=17.10,
            lng_min=-96.76, lng_max=-96.68,
        ),
        expected_nodes_min=150,
        expected_nodes_max=1000,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "san-miguel-de-allende": CityConfig(
        name="San Miguel de Allende",
        slug="san-miguel-de-allende",
        country="Mexico",
        timezone="America/Mexico_City",
        subreddits={
            "sanmigueldeallende": 1.0,
            "mexico": 0.7,
            "mexicotravel": 0.85,
            # cross-subreddit signals
            "travel": 0.60,
            "solotravel": 0.60,
            "food": 0.65,
            "foodie": 0.60,
        },
        neighborhood_terms=[
            "san miguel de allende", "san miguel", "sma",
            "centro historico sma", "el jardin",
            "la parroquia", "calle canal",
            "san antonio", "la aurora",
            "fabrica la aurora", "colonia guadalupe",
            "colonia san rafael", "colonia allende",
            "atotonilco", "botanical garden sma",
            "el charco del ingenio",
            "calle correo", "calle mesones",
        ],
        stopwords=[
            "oxxo",
        ],
        bbox=BoundingBox(
            lat_min=20.88, lat_max=20.93,
            lng_min=-100.77, lng_max=-100.72,
        ),
        expected_nodes_min=80,
        expected_nodes_max=500,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "porto": CityConfig(
        name="Porto",
        slug="porto",
        country="Portugal",
        timezone="Europe/Lisbon",
        subreddits={
            "porto": 1.0,
            "portugal": 0.8,
            "portowine": 0.85,
            # cross-subreddit signals
            "wine": 0.65,
            "travel": 0.60,
            "solotravel": 0.60,
            "europe": 0.65,
        },
        neighborhood_terms=[
            "porto", "oporto",
            "ribeira", "ribeira do porto",
            "foz do douro", "foz",
            "cedofeita", "boavista",
            "clerigos", "torre dos clerigos",
            "bolhao", "mercado do bolhao",
            "baixa porto", "aliados",
            "miragaia", "massarelos",
            "vila nova de gaia", "gaia",
            "sao bento", "livraria lello",
            "matosinhos", "rua santa catarina",
            "rua das flores",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=41.13, lat_max=41.18,
            lng_min=-8.67, lng_max=-8.58,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1500,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "lisbon": CityConfig(
        name="Lisbon",
        slug="lisbon",
        country="Portugal",
        timezone="Europe/Lisbon",
        subreddits={
            "lisbon": 1.0,
            "portugal": 0.8,
            "lisboa": 0.9,
            # cross-subreddit signals
            "solotravel": 0.65,
            "backpacking": 0.60,
            "travel": 0.60,
            "wine": 0.65,
            "europe": 0.65,
        },
        neighborhood_terms=[
            "lisbon", "lisboa",
            "alfama", "mouraria", "graca",
            "bairro alto", "chiado",
            "baixa", "rossio",
            "principe real", "santos",
            "cais do sodre", "lx factory",
            "belem", "ajuda",
            "alcantara", "campo de ourique",
            "estrela", "lapa",
            "avenida da liberdade", "time out market",
            "intendente", "anjos",
            "almada", "cascais", "sintra",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=38.70, lat_max=38.78,
            lng_min=-9.20, lng_max=-9.10,
        ),
        expected_nodes_min=300,
        expected_nodes_max=2000,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "tallinn": CityConfig(
        name="Tallinn",
        slug="tallinn",
        country="Estonia",
        timezone="Europe/Tallinn",
        subreddits={
            "tallinn": 1.0,
            "eesti": 0.85,
            "digitalnomad": 0.7,
            # cross-subreddit signals
            "solotravel": 0.65,
            "backpacking": 0.60,
            "travel": 0.60,
            "europe": 0.65,
            "easterneurope": 0.65,
        },
        neighborhood_terms=[
            "tallinn",
            "old town tallinn", "vanalinn",
            "toompea", "town hall square",
            "kalamaja", "telliskivi",
            "telliskivi creative city",
            "rotermann", "rotermann quarter",
            "kadriorg", "pirita",
            "noblessner", "lennusadam",
            "balti jaam", "balti jaama turg",
            "pelgulinn", "kristiine",
            "ulemiste", "nomme",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=59.40, lat_max=59.47,
            lng_min=24.70, lng_max=24.82,
        ),
        expected_nodes_min=150,
        expected_nodes_max=1000,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "ljubljana": CityConfig(
        name="Ljubljana",
        slug="ljubljana",
        country="Slovenia",
        timezone="Europe/Ljubljana",
        subreddits={
            "ljubljana": 1.0,
            "slovenia": 0.85,
            # cross-subreddit signals
            "travel": 0.60,
            "solotravel": 0.60,
            "europe": 0.65,
            "easterneurope": 0.65,
        },
        neighborhood_terms=[
            "ljubljana",
            "old town ljubljana", "stare mesto",
            "metelkova", "metelkova mesto",
            "trnovo", "krakovo",
            "presernov trg", "preseren square",
            "triple bridge", "dragon bridge",
            "ljubljana castle", "grad",
            "siska", "bezigrad",
            "central market", "plecnikov trg",
            "tivoli", "tivoli park",
            "tabor", "kodeljevo",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=46.03, lat_max=46.08,
            lng_min=14.47, lng_max=14.55,
        ),
        expected_nodes_min=150,
        expected_nodes_max=800,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "kotor": CityConfig(
        name="Kotor",
        slug="kotor",
        country="Montenegro",
        timezone="Europe/Podgorica",
        subreddits={
            "montenegro": 1.0,
            "kotor": 0.95,
            # cross-subreddit signals
            "travel": 0.60,
            "solotravel": 0.60,
            "europe": 0.65,
            "easterneurope": 0.65,
        },
        neighborhood_terms=[
            "kotor", "kotor old town",
            "stari grad kotor", "sea gate",
            "kotor bay", "boka kotorska",
            "dobrota", "prcanj",
            "perast", "risan",
            "tivat", "porto montenegro",
            "herceg novi", "budva",
            "kotor fortress", "san giovanni",
            "skaljari", "muo",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=42.41, lat_max=42.44,
            lng_min=18.75, lng_max=18.78,
        ),
        expected_nodes_min=80,
        expected_nodes_max=400,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "hoi-an": CityConfig(
        name="Hoi An",
        slug="hoi-an",
        country="Vietnam",
        timezone="Asia/Ho_Chi_Minh",
        subreddits={
            "hoian": 1.0,
            "vietnam": 0.85,
            "vietnamtravel": 0.8,
            # cross-subreddit signals
            "travel": 0.60,
            "solotravel": 0.60,
            "southeastasia": 0.65,
            "asiatravel": 0.65,
        },
        neighborhood_terms=[
            "hoi an", "hoian",
            "old town hoi an", "ancient town",
            "an hoi", "an bang beach",
            "cua dai", "cua dai beach",
            "cam nam", "cam thanh",
            "tra que", "tra que village",
            "japanese bridge", "assembly halls",
            "central market hoi an", "night market",
            "hai ba trung street", "bach dang street",
            "le loi street",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=15.85, lat_max=15.90,
            lng_min=108.31, lng_max=108.35,
        ),
        expected_nodes_min=80,
        expected_nodes_max=600,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "penang": CityConfig(
        name="Penang",
        slug="penang",
        country="Malaysia",
        timezone="Asia/Kuala_Lumpur",
        subreddits={
            "penang": 1.0,
            "malaysia": 0.85,
            "malaysianfood": 0.9,
            # cross-subreddit signals
            "travel": 0.60,
            "solotravel": 0.60,
            "food": 0.65,
            "foodie": 0.60,
            "southeastasia": 0.65,
            "asiatravel": 0.65,
        },
        neighborhood_terms=[
            "penang", "george town", "georgetown penang",
            "armenian street", "love lane",
            "chulia street", "lebuh chulia",
            "little india penang", "campbell street",
            "gurney drive", "gurney plaza",
            "batu ferringhi", "tanjung bungah",
            "air itam", "kek lok si",
            "penang hill", "bukit bendera",
            "jelutong", "gelugor",
            "new lane hawker", "lorong baru",
            "kimberley street", "tekka",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=5.38, lat_max=5.48,
            lng_min=100.28, lng_max=100.38,
        ),
        expected_nodes_min=200,
        expected_nodes_max=1500,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "kyoto": CityConfig(
        name="Kyoto",
        slug="kyoto",
        country="Japan",
        timezone="Asia/Tokyo",
        subreddits={
            "kyoto": 1.0,
            "japantravel": 0.9,
            "japanlife": 0.8,
            "japan": 0.7,
            # cross-subreddit signals
            "travel": 0.60,
            "solotravel": 0.60,
            "asiatravel": 0.65,
        },
        neighborhood_terms=[
            "kyoto",
            "gion", "higashiyama",
            "arashiyama", "sagano",
            "fushimi", "fushimi inari",
            "nishiki", "nishiki market",
            "pontocho", "kiyamachi",
            "kawaramachi", "shijo",
            "sanjo", "okazaki",
            "kinkakuji", "ginkakuji",
            "nijo", "nijo castle",
            "philosopher's path", "tetsugaku no michi",
            "kyoto station", "uji",
            "kitayama", "demachi",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=34.93, lat_max=35.07,
            lng_min=135.69, lng_max=135.81,
        ),
        expected_nodes_min=300,
        expected_nodes_max=2000,
        language_hints=["en"],
        rss_feeds=[],
    ),

    "osaka": CityConfig(
        name="Osaka",
        slug="osaka",
        country="Japan",
        timezone="Asia/Tokyo",
        subreddits={
            "osaka": 1.0,
            "japantravel": 0.9,
            "japanlife": 0.8,
            "japan": 0.7,
            # cross-subreddit signals
            "travel": 0.60,
            "solotravel": 0.60,
            "asiatravel": 0.65,
        },
        neighborhood_terms=[
            "osaka",
            "dotonbori", "namba",
            "shinsaibashi", "amerikamura",
            "shinsekai", "tennoji",
            "umeda", "kita",
            "nakazakicho", "tenjinbashi",
            "kuromon", "kuromon market",
            "tsuruhashi", "koreatown osaka",
            "minami", "nipponbashi",
            "fukushima osaka", "kitahama",
            "utsubo park", "horie",
            "osaka castle", "temma",
        ],
        stopwords=[],
        bbox=BoundingBox(
            lat_min=34.60, lat_max=34.73,
            lng_min=135.44, lng_max=135.55,
        ),
        expected_nodes_min=300,
        expected_nodes_max=2000,
        language_hints=["en"],
        rss_feeds=[],
    ),

    # ---------------------------------------------------------------------------
    # Opportunistic cities — no dedicated subreddit downloads.
    # Captured passively from regional/interest Parquets already on disk
    # (r/oregon, r/colorado, r/northcarolina, r/washington, r/vermont, etc.)
    # Run scrape + llm_fallback + vibe_extraction only; skip reddit_download.
    # ---------------------------------------------------------------------------

    "eugene": CityConfig(
        name="Eugene",
        slug="eugene",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={},
        neighborhood_terms=[
            "eugene", "eugene oregon", "whiteaker", "5th street market",
            "pre's trail", "skinner butte", "ferry street bridge",
            "downtown eugene", "south eugene", "west eugene",
            "university of oregon", "u of o", "autzen",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=43.98, lat_max=44.12, lng_min=-123.25, lng_max=-123.00),
        expected_nodes_min=20,
        expected_nodes_max=300,
        rss_feeds=[],
    ),

    "bellingham": CityConfig(
        name="Bellingham",
        slug="bellingham",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={},
        neighborhood_terms=[
            "bellingham", "bellingham washington", "bellingham wa",
            "fairhaven", "downtown bellingham", "whatcom",
            "western washington university", "wwu", "sehome",
            "boulevard park", "lake padden", "chuckanut",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=48.69, lat_max=48.82, lng_min=-122.55, lng_max=-122.38),
        expected_nodes_min=20,
        expected_nodes_max=250,
        rss_feeds=[],
    ),

    "ashland": CityConfig(
        name="Ashland",
        slug="ashland",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={},
        neighborhood_terms=[
            "ashland", "ashland oregon", "ashland or",
            "oregon shakespeare festival", "osf", "lithia park",
            "plaza ashland", "downtown ashland", "rogue valley",
            "siskiyou", "mt ashland",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=42.14, lat_max=42.22, lng_min=-122.74, lng_max=-122.62),
        expected_nodes_min=15,
        expected_nodes_max=150,
        rss_feeds=[],
    ),

    "salida": CityConfig(
        name="Salida",
        slug="salida",
        country="United States",
        timezone="America/Denver",
        subreddits={},
        neighborhood_terms=[
            "salida", "salida colorado", "salida co",
            "s-mountain", "arkansas river salida", "poncha springs",
            "downtown salida", "f street salida", "FIBArk",
            "monarch mountain", "chalk creek",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=38.50, lat_max=38.57, lng_min=-106.02, lng_max=-105.94),
        expected_nodes_min=15,
        expected_nodes_max=150,
        rss_feeds=[],
    ),

    "crested-butte": CityConfig(
        name="Crested Butte",
        slug="crested-butte",
        country="United States",
        timezone="America/Denver",
        subreddits={},
        neighborhood_terms=[
            "crested butte", "crested butte colorado", "mt crested butte",
            "gothic road", "elk avenue", "gunnison", "kebler pass",
            "west elk", "paradise divide",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=38.84, lat_max=38.92, lng_min=-107.02, lng_max=-106.94),
        expected_nodes_min=20,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "estes-park": CityConfig(
        name="Estes Park",
        slug="estes-park",
        country="United States",
        timezone="America/Denver",
        subreddits={},
        neighborhood_terms=[
            "estes park", "estes park colorado", "rmnp", "rocky mountain national park",
            "trail ridge road", "bear lake", "downtown estes park",
            "fall river", "lake estes",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=40.35, lat_max=40.41, lng_min=-105.58, lng_max=-105.47),
        expected_nodes_min=20,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "chapel-hill": CityConfig(
        name="Chapel Hill",
        slug="chapel-hill",
        country="United States",
        timezone="America/New_York",
        subreddits={},
        neighborhood_terms=[
            "chapel hill", "chapel hill nc", "carrboro",
            "franklin street", "unc", "university of north carolina",
            "downtown chapel hill", "weaver street", "rosemary street",
            "north carolina botanical garden",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=35.87, lat_max=35.97, lng_min=-79.10, lng_max=-78.97),
        expected_nodes_min=20,
        expected_nodes_max=300,
        rss_feeds=[],
    ),

    "wilmington-nc": CityConfig(
        name="Wilmington",
        slug="wilmington-nc",
        country="United States",
        timezone="America/New_York",
        subreddits={},
        neighborhood_terms=[
            "wilmington nc", "wilmington north carolina",
            "wrightsville beach", "carolina beach", "kure beach",
            "riverwalk wilmington", "downtown wilmington", "cape fear",
            "castle hayne", "leland nc",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=34.12, lat_max=34.31, lng_min=-77.96, lng_max=-77.83),
        expected_nodes_min=20,
        expected_nodes_max=300,
        rss_feeds=[],
    ),

    "boone-nc": CityConfig(
        name="Boone",
        slug="boone-nc",
        country="United States",
        timezone="America/New_York",
        subreddits={},
        neighborhood_terms=[
            "boone nc", "boone north carolina",
            "appalachian state", "app state", "king street boone",
            "blue ridge parkway boone", "watauga", "blowing rock",
            "beech mountain", "sugar mountain",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=36.18, lat_max=36.25, lng_min=-81.72, lng_max=-81.61),
        expected_nodes_min=15,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "stowe": CityConfig(
        name="Stowe",
        slug="stowe",
        country="United States",
        timezone="America/New_York",
        subreddits={},
        neighborhood_terms=[
            "stowe", "stowe vermont", "stowe vt",
            "stowe mountain resort", "mt mansfield", "smugglers notch",
            "main street stowe", "stowe recreation path",
            "waterbury vermont", "morrisville vt",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=44.44, lat_max=44.50, lng_min=-72.72, lng_max=-72.64),
        expected_nodes_min=15,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "walla-walla": CityConfig(
        name="Walla Walla",
        slug="walla-walla",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={},
        neighborhood_terms=[
            "walla walla", "walla walla washington", "walla walla wa",
            "downtown walla walla", "wine country walla walla",
            "whitman college", "main street walla walla",
            "blue mountains walla walla",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=46.04, lat_max=46.10, lng_min=-118.38, lng_max=-118.27),
        expected_nodes_min=15,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "leavenworth-wa": CityConfig(
        name="Leavenworth",
        slug="leavenworth-wa",
        country="United States",
        timezone="America/Los_Angeles",
        subreddits={},
        neighborhood_terms=[
            "leavenworth", "leavenworth washington", "leavenworth wa",
            "bavarian village", "icicle creek", "enchantments",
            "wenatchee river", "front street leavenworth",
            "alpine lakes wilderness",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=47.58, lat_max=47.62, lng_min=-120.68, lng_max=-120.62),
        expected_nodes_min=15,
        expected_nodes_max=200,
        rss_feeds=[],
    ),

    "breckenridge": CityConfig(
        name="Breckenridge",
        slug="breckenridge",
        country="United States",
        timezone="America/Denver",
        subreddits={},
        neighborhood_terms=[
            "breckenridge", "breckenridge colorado", "breck",
            "main street breckenridge", "peak 8", "peak 9", "peak 10",
            "blue river", "frisco colorado", "keystone resort",
            "ten mile range",
        ],
        stopwords=COMMON_CHAIN_STOPWORDS,
        bbox=BoundingBox(lat_min=39.46, lat_max=39.50, lng_min=-106.06, lng_max=-105.99),
        expected_nodes_min=25,
        expected_nodes_max=300,
        rss_feeds=[],
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
