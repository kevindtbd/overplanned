"""
Quick synthetic ActivityNode seeder for dev/training.

Generates realistic-sounding activity nodes across all 11 categories
for specified cities. NOT the real scraping pipeline — just DB inserts
with plausible names, coords, and quality signals.

Used to populate enough nodes for the cartesian persona seeder to work
with diverse item exposure across categories.

Usage:
    DATABASE_URL=... python3 -m services.api.pipeline.city_node_seeder
"""

import asyncio
import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# City data: real neighborhoods, realistic coordinates, local flavor
# ---------------------------------------------------------------------------

CITIES: dict[str, dict[str, Any]] = {
    "New York": {
        "country": "United States",
        "timezone": "America/New_York",
        "center": (40.7580, -73.9855),
        "neighborhoods": [
            "Lower East Side", "Williamsburg", "Bushwick", "Greenwich Village",
            "East Village", "SoHo", "Chinatown", "Harlem", "Astoria",
            "Park Slope", "Red Hook", "Chelsea", "Hell's Kitchen",
            "Upper West Side", "Dumbo", "Bed-Stuy", "Crown Heights",
            "Fort Greene", "Prospect Heights", "Tribeca",
        ],
        "nodes": {
            "dining": [
                ("Di Fara Pizza", "Legendary thin-crust pizza, cash only, worth the line"),
                ("Xi'an Famous Foods", "Hand-pulled noodles and cumin lamb, Chinatown staple"),
                ("Los Tacos No.1", "Standing-room taqueria in Chelsea Market, al pastor is the move"),
                ("Joe's Shanghai", "Soup dumplings that defined a generation of NYC Chinese food"),
                ("Russ & Daughters", "Century-old appetizing shop, lox and schmear institution"),
                ("Lucali", "BYOB pizza in Carroll Gardens, no slices, no reservations, no regrets"),
                ("Bunna Cafe", "Ethiopian vegan in Bushwick, injera platters and honey wine"),
                ("Nom Wah Tea Parlor", "Oldest dim sum in Chinatown, still fire"),
                ("Superiority Burger", "Tiny East Village vegetarian counter, lines around the block"),
                ("L'Artusi", "West Village Italian, handmade pasta, natural wine list"),
                ("Katz's Delicatessen", "Pastrami institution since 1888, no shortcuts"),
                ("Thai Diner", "Nolita Thai-American mashup, khao soi and egg waffle desserts"),
            ],
            "drinks": [
                ("Attaboy", "No-menu cocktail bar in a Lower East Side closet"),
                ("Bemelmans Bar", "Old-money jazz bar at the Carlyle, murals by the Madeline guy"),
                ("Dead Rabbit", "Three-floor Irish cocktail palace in FiDi"),
                ("Sunny's Bar", "Red Hook dive legend, live bluegrass on Saturdays"),
                ("Please Don't Tell", "Enter through a phone booth in a hot dog shop"),
                ("Bar Goto", "Bartender Kenta Goto's Lower East Side gem, Japanese-inflected cocktails"),
                ("Nowadays", "Ridgewood outdoor bar and event space, all-day DJ sets in summer"),
                ("Maison Premiere", "Williamsburg absinthe bar with oysters and New Orleans energy"),
            ],
            "culture": [
                ("The Met Cloisters", "Medieval art in a reconstructed monastery overlooking the Hudson"),
                ("MoMA PS1", "Contemporary art in a converted Long Island City schoolhouse"),
                ("Tenement Museum", "Lower East Side immigration history, walk-through apartments"),
                ("Noguchi Museum", "Isamu Noguchi's studio-turned-museum in Long Island City"),
                ("New Museum", "Bowery contemporary art, always provocative"),
                ("The Morgan Library", "Pierpont Morgan's personal library, Renaissance manuscripts"),
                ("Museum of the Moving Image", "Film and media history in Astoria"),
                ("El Museo del Barrio", "Latino art and culture on Museum Mile"),
            ],
            "outdoors": [
                ("The Highline", "Elevated park on former rail line, Chelsea to Hudson Yards"),
                ("Prospect Park", "Olmsted's favorite (not Central Park), wilder and less crowded"),
                ("Governors Island", "Car-free island with views, hammocks, and summer art installations"),
                ("Jamaica Bay Wildlife Refuge", "Birdwatching oasis inside the city limits"),
                ("Brooklyn Bridge Park", "Waterfront park with Manhattan skyline views"),
                ("Fort Tilden", "Abandoned military base turned beach, Rockaway Peninsula"),
                ("Green-Wood Cemetery", "Gothic Revival grounds, better than most city parks"),
            ],
            "active": [
                ("Brooklyn Boulders", "Climbing gym in Gowanus with coworking"),
                ("Rockaway Beach Surf", "Learn to surf without leaving NYC"),
                ("Chelsea Piers", "Sports complex on the Hudson, everything from golf to gymnastics"),
                ("Central Park Bike Loop", "6.1-mile loop, sunrise rides before the tourists"),
                ("Red Bull Half Court", "3v3 streetball tournaments, Rucker Park energy"),
            ],
            "entertainment": [
                ("Sleep No More", "Immersive theater in a fake McKittrick Hotel, wear a mask"),
                ("Comedy Cellar", "Greenwich Village comedy institution, surprise drop-ins"),
                ("Smalls Jazz Club", "West Village basement jazz, late sets till 4am"),
                ("Meow Wolf", "Immersive art experience, recently opened in Brooklyn"),
                ("Film Forum", "Independent cinema, double features, repertory classics"),
                ("House of Yes", "Bushwick performance venue, circus acts and themed parties"),
            ],
            "shopping": [
                ("Strand Book Store", "18 miles of books on Broadway, since 1927"),
                ("Artists & Fleas", "Williamsburg weekend market, vintage and handmade"),
                ("The Lot Radio", "Greenpoint flea market next to the shipping container radio station"),
                ("Canal Street Market", "Curated food and retail in Chinatown"),
                ("Brooklyn Flea", "Dumbo vintage market, antiques and smoked meat"),
                ("Tokio 7", "East Village consignment, Japanese and designer pieces"),
            ],
            "experience": [
                ("Staten Island Ferry", "Free boat ride, best skyline view in the city"),
                ("Coney Island", "Boardwalk, Nathan's, Wonder Wheel, peak NYC summer"),
                ("Smorgasburg", "Outdoor food market, 100+ vendors, Williamsburg and Prospect Park"),
                ("Roosevelt Island Tram", "Aerial tramway across the East River, $2.90 commute"),
                ("The Vessel", "Honeycomb staircase at Hudson Yards, love it or hate it"),
                ("City Island", "Tiny fishing village in the Bronx, feels like New England"),
            ],
            "nightlife": [
                ("Basement", "Chinatown techno club, no bottle service, no attitude"),
                ("House of Yes", "Bushwick queer performance venue, themed nights"),
                ("Good Room", "Greenpoint two-room club, house and disco"),
                ("Nowadays", "Ridgewood warehouse vibes, outdoor dance floor in summer"),
                ("Jupiter Disco", "Intimate Williamsburg DJ bar, no cover most nights"),
                ("Bossa Nova Civic Club", "Bushwick institution, weird and wonderful bookings"),
            ],
            "group_activity": [
                ("Escape room at Mission Escape", "Midtown puzzle rooms, timed team challenges"),
                ("Brooklyn Bowl", "Live music and bowling in Williamsburg"),
                ("Spyscape", "Interactive spy museum near Times Square"),
                ("DUMBO Archway Market", "Under-the-bridge food and performance space"),
                ("The Rink at Rockefeller Center", "Ice skating under the tree, peak tourist but peak vibes"),
            ],
            "wellness": [
                ("Aire Ancient Baths", "Roman-style thermal baths in Tribeca"),
                ("Bathhouse", "Williamsburg bathhouse, sauna, cold plunge, rooftop"),
                ("Sky Ting Yoga", "Chinatown and Tribeca locations, donation-based community classes"),
                ("QC NY Spa", "Governors Island spa with infinity pool and Manhattan views"),
                ("Great Jones Spa", "NoHo day spa with water lounge, been there forever"),
            ],
        },
    },
    "Mexico City": {
        "country": "Mexico",
        "timezone": "America/Mexico_City",
        "center": (19.4326, -99.1332),
        "neighborhoods": [
            "Roma Norte", "Condesa", "Coyoacan", "Polanco", "Centro Historico",
            "Juarez", "San Rafael", "Santa Maria la Ribera", "Xochimilco",
            "San Angel", "Del Valle", "Narvarte", "Doctores", "Tlalpan",
            "Chapultepec", "Cuauhtemoc", "Escandon", "Mixcoac", "Tacubaya",
        ],
        "nodes": {
            "dining": [
                ("Contramar", "Roma tostada de atun and grilled fish, the lunch scene"),
                ("El Huequito", "Al pastor tacos since 1959, Centro Historico institution"),
                ("Pujol", "Enrique Olvera's tasting menu, mole madre is transcendent"),
                ("Taqueria Orinoco", "Roma Norte breakfast tacos, machaca and chicharron"),
                ("Cafe de Tacuba", "Historic Centro cafe, enchiladas suizas since 1912"),
                ("Mercado Roma", "Roma food hall, upscale street food and craft beer"),
                ("El Vilsito", "Mechanic shop by day, taco stand by night, Narvarte legend"),
                ("Quintonil", "Jorge Vallejo's seasonal Mexican fine dining, Polanco"),
                ("Los Cocuyos", "Centro Historico late-night street tacos, suadero and longaniza"),
                ("Expendio de Maiz", "Corn-focused tasting menu by hand in Roma, no menu, trust the chef"),
                ("El Califa de Leon", "Michelin-starred taco stand, two items only, both perfect"),
                ("Lardo", "Condesa Mediterranean-Mexican brunch, always a wait"),
            ],
            "drinks": [
                ("Licoreria Limantour", "World's Best Bar list regular, Roma cocktails"),
                ("Baltra Bar", "Mezcal-forward cocktail bar in Roma Norte"),
                ("Xaman Bar", "Coyoacan speakeasy, pre-Hispanic ingredient cocktails"),
                ("La Clandestina", "Standing-room mezcaleria in Condesa, flights and conversation"),
                ("Hanky Panky", "Secretive cocktail bar, you need the address"),
                ("Pulqueria Los Insurgentes", "Traditional pulque bar, cured flavors, Juarez"),
                ("Departamento", "Rooftop bar in Roma, sunset mezcal and city views"),
                ("La Botica", "Mezcal apothecary in Centro, 200+ bottles"),
            ],
            "culture": [
                ("Museo Nacional de Antropologia", "World-class pre-Columbian collection in Chapultepec"),
                ("Museo Frida Kahlo", "The Blue House in Coyoacan, intimate and iconic"),
                ("Palacio de Bellas Artes", "Art Deco palace, Rivera and Orozco murals inside"),
                ("Museo Tamayo", "Contemporary art in Chapultepec, brutalist architecture"),
                ("Museo Soumaya", "Carlos Slim's private collection, free entry, wild architecture"),
                ("Templo Mayor", "Aztec ruins in the literal center of the city"),
                ("MUAC", "UNAM campus contemporary art, always free, always good"),
                ("Museo Jumex", "Contemporary art in Polanco, David Chipperfield building"),
            ],
            "outdoors": [
                ("Bosque de Chapultepec", "Massive urban forest, bigger than Central Park"),
                ("Xochimilco Canals", "Floating gardens on colorful trajineras, mariachi optional"),
                ("Desierto de los Leones", "Pine forest national park at the edge of the city"),
                ("Viveros de Coyoacan", "Tree nursery turned jogging park, peaceful mornings"),
                ("Parque Mexico", "Condesa art deco park, dog-friendly, Sunday market"),
                ("Cerro de la Estrella", "Hill with Aztec pyramid ruins and city panorama"),
                ("Parque Hundido", "Sunken park in Del Valle, replicas of pre-Columbian sculptures"),
            ],
            "active": [
                ("Lucha Libre at Arena Mexico", "Professional wrestling spectacle, Tuesday and Friday nights"),
                ("Climbing at Rockodromo", "Bouldering gym in Roma Norte"),
                ("Ciclovia Reforma", "Car-free Sunday cycling on Paseo de la Reforma"),
                ("Club America at Estadio Azteca", "Liga MX match in the legendary stadium"),
                ("Pickup basketball at Parque Espana", "Condesa courts, competitive runs"),
            ],
            "entertainment": [
                ("Lucha Libre at Arena Coliseo", "Smaller, grittier wrestling venue, more local"),
                ("Cine Tonala", "Independent cinema and live music in Roma"),
                ("Salon Los Angeles", "Classic dancehall, salsa and cumbia since 1937"),
                ("Foro Shakespeare", "Experimental theater in Condesa"),
                ("Cineteca Nacional", "National film archive with screenings and festivals"),
                ("Teatro de la Ciudad", "Grand theater in Centro, ballet and symphonic performances"),
            ],
            "shopping": [
                ("Mercado de la Ciudadela", "Traditional crafts market, best prices for artisanal goods"),
                ("Tianguis del Chopo", "Saturday punk and alternative market near Santa Maria"),
                ("Mercado de Sonora", "Mystical market, herbs, potions, and alebrijes"),
                ("Centro de Artesanias La Ciudadela", "One-stop shop for Mexican crafts and textiles"),
                ("El Bazar Sabado", "Saturday art market in San Angel, quality ceramics and jewelry"),
                ("Mercado de Jamaica", "Massive flower market, also sells produce and prepared food"),
            ],
            "experience": [
                ("Teotihuacan Pyramids", "Sun and Moon pyramids, 45 min from the city"),
                ("Ballet Folklorico", "Traditional dance at Bellas Artes, Wednesday and Sunday"),
                ("Garibaldi Plaza at Night", "Mariachi square, hire a band for your table"),
                ("Floating Market at Xochimilco", "Food vendors on boats pulling up to your trajinera"),
                ("Zocalo Flag Ceremony", "Daily flag lowering at the main square, military precision"),
                ("Day of the Dead at Mixquic", "November 1-2, candlelit cemetery tradition"),
            ],
            "nightlife": [
                ("Patrick Miller", "Legendary dancehall, Friday night high-energy freestyle"),
                ("AM Local", "Roma Norte DJ bar, house and techno"),
                ("Departamento", "Multi-floor club in Roma, rooftop and basement"),
                ("Foro Hilvana", "Underground electronic music venue, Doctores"),
                ("Yu Yu", "Late-night Condesa, Asian-Mexican food and DJ sets"),
                ("Salon Rios", "Cumbia and tropical dance nights, old-school vibes"),
            ],
            "group_activity": [
                ("Lucha Libre VIP Experience", "Ringside seats with masks and micheladas"),
                ("Mexican Cooking Class at Casa Jacaranda", "Hands-on mole and tortilla making in Roma"),
                ("Pulque Tour in Centro", "Walk between traditional pulquerias"),
                ("Xochimilco Party Trajinera", "Rent a boat with speakers, BYOB, float party"),
                ("Escape Room Mexico", "Themed rooms in Roma Norte and Polanco"),
            ],
            "wellness": [
                ("Temazcal Ceremony", "Pre-Hispanic sweat lodge experience outside the city"),
                ("QI Spa at W Hotel", "Polanco luxury spa, hydrotherapy circuit"),
                ("Yoga at Parque Mexico", "Free Sunday morning sessions in Condesa"),
                ("Barranca del Muerto Hot Springs", "Natural thermal springs south of the city"),
                ("Float Lab Roma", "Sensory deprivation float tanks in Roma Norte"),
            ],
        },
    },
    "Bend": {
        "country": "United States",
        "timezone": "America/Los_Angeles",
        "center": (44.0582, -121.3153),
        "neighborhoods": [
            "Downtown Bend", "Old Mill District", "Westside",
            "NorthWest Crossing", "Midtown", "South Bend",
            "River West", "Awbrey Butte", "Boyd Acres",
        ],
        "nodes": {
            "dining": [
                ("Spork", "Eclectic small plates, local ingredients, always changing menu"),
                ("Jackson's Corner", "Farm-to-table bakery and restaurant, wood-fired everything"),
                ("Zydeco Kitchen & Cocktails", "Southern-inspired comfort food in the Old Mill"),
                ("Bos Taurus", "Steakhouse with local rancher sourcing, NW Crossing gem"),
                ("Joolz", "Middle Eastern mezze and kebabs, family-run, Westside favorite"),
                ("Ariana", "Afghan cuisine in a strip mall, best lamb in Central Oregon"),
                ("Wild Rose Thai", "Thai street food staples, locals-only lunch spot"),
                ("Bangers & Brews", "Gourmet sausages and craft beer, downtown casual"),
                ("Drake", "New American dinner spot, seasonal tasting menu option"),
                ("El Sancho", "Taco cart turned brick-and-mortar, carnitas are the move"),
            ],
            "drinks": [
                ("Deschutes Brewery", "The OG Bend brewery, Mirror Pond on tap since 1988"),
                ("Boneyard Beer", "Hop-forward IPAs brewed in a former auto shop"),
                ("Crux Fermentation Project", "South Bend brewery with Cascade views and food trucks"),
                ("Bend Brewing Company", "Brewpub overlooking Mirror Pond, sunset pints"),
                ("The Lot", "Food cart pod with covered bar area, great rotating taps"),
                ("Spoken Moto", "Motorcycle-themed bar and coffee shop, vintage vibes"),
                ("Worthy Brewing", "Brewery with rooftop observatory and hop garden tours"),
                ("McMenamins Old St. Francis", "Historic school turned brewpub, soaking pool and theater"),
            ],
            "culture": [
                ("High Desert Museum", "Living museum with raptor shows, porcupines, and regional history"),
                ("Bend Art Center", "Community art gallery and classes, rotating local exhibitions"),
                ("Tower Theatre", "Restored 1940s movie palace, now live music and film"),
                ("Old Mill Heritage Walk", "Self-guided history trail through the former lumber mill district"),
                ("Sunriver Nature Center", "Observatory and botanical garden south of Bend"),
                ("Deschutes Historical Museum", "Pioneer and Native American history of Central Oregon"),
            ],
            "outdoors": [
                ("Smith Rock State Park", "World-class sport climbing and hiking, Monkey Face spire"),
                ("Deschutes River Trail", "12-mile paved path along the river through town"),
                ("Tumalo Falls", "97-foot waterfall, short hike from trailhead, postcard views"),
                ("Pilot Butte", "Cinder cone in the middle of town, 360-degree Cascade views"),
                ("Todd Lake", "Alpine lake at 6,000 ft, wildflower meadows in summer"),
                ("Shevlin Park", "Forested canyon park, trail running and mountain biking"),
                ("Lava River Cave", "Mile-long lava tube, bring layers (it's 42F year-round)"),
                ("Newberry Volcanic Monument", "Obsidian flows, crater lakes, and lava casts"),
                ("Sparks Lake", "Paddle-in alpine lake with South Sister reflections"),
            ],
            "active": [
                ("Mt. Bachelor", "Ski area with 3,365 ft vertical, also summer lift-accessed hiking"),
                ("Phil's Trail Complex", "Premier mountain bike trail network, flow and tech"),
                ("Wanoga Snow Park", "Nordic skiing and snowshoeing, groomed trails"),
                ("Bend Whitewater Park", "Engineered rapids on the Deschutes, SUP and kayak"),
                ("Sunriver Resort Bike Paths", "15+ miles of paved paths through the resort community"),
                ("Paulina Plunge", "Downhill mountain bike descent from Newberry Crater, guided"),
            ],
            "entertainment": [
                ("McMenamins Old St. Francis Theater", "Second-run movies with beer and pizza in a chapel"),
                ("Volcanic Theatre Pub", "Live music venue, local and touring acts, all ages"),
                ("Bend Comedy Night", "Weekly standup at rotating downtown venues"),
                ("Hayden Homes Amphitheater", "Outdoor concert venue on the river, summer shows"),
                ("Regal Old Mill", "Multiplex in the Old Mill District, IMAX screen"),
            ],
            "shopping": [
                ("The Village at Sunriver", "Outdoor shopping village with local boutiques"),
                ("Old Mill District Shops", "Converted lumber mill, REI flagship and local stores"),
                ("Dudley's Bookshop Cafe", "Independent bookstore and coffee, downtown staple"),
                ("Patagonia Bend", "Flagship outdoor store, repair station and local guides"),
                ("Cowgirl Cash", "Vintage Western wear and antiques, one-of-a-kind finds"),
                ("Hot Box Betty", "Secondhand and vintage clothing, Midtown"),
            ],
            "experience": [
                ("Wanderlust Tours Cave Exploration", "Guided lava tube tours with naturalist guides"),
                ("Bend Ale Trail", "Self-guided passport to 30+ breweries, earn prizes"),
                ("Stand Up Paddle the Deschutes", "SUP rentals and guided floats through town"),
                ("Cascade Lakes Scenic Byway", "66-mile drive past lakes, volcanoes, and lava fields"),
                ("Sunriver Observatory Stargazing", "Dark-sky astronomy programs, telescope viewing"),
                ("Float the Deschutes", "Lazy river float from Riverbend Park to Drake Park"),
            ],
            "nightlife": [
                ("Astro Lounge", "Downtown cocktail bar, DJ sets on weekends"),
                ("The Capitol", "Live music and dance floor, Bend's late-night anchor"),
                ("Velvet", "Wine bar turned late-night spot, curated playlists"),
                ("Silver Moon Brewing", "Brewery taproom with live music and comedy nights"),
                ("Washington", "Craft cocktails in a speakeasy-style downtown basement"),
            ],
            "group_activity": [
                ("Bend Brew Bus", "Guided brewery tour by bus, 3-4 stops with tastings"),
                ("Escape Room Bend", "Themed puzzle rooms downtown, book ahead for groups"),
                ("Tumalo Creek Kayak & Canoe", "Group paddle trips on the Deschutes and Cascade lakes"),
                ("Bend Food Tours", "Walking food tour through downtown, 5-6 stops"),
                ("Goat Yoga at Laughing Goat Farm", "Exactly what it sounds like, surprisingly fun"),
            ],
            "wellness": [
                ("McMenamins Turkish Bath", "Cedar soaking pool at Old St. Francis, open late"),
                ("Bend Hot Springs (concept)", "Natural hot springs access via forest roads"),
                ("Namaspa", "Yoga and massage studio, Westside, drop-in classes"),
                ("Shibui Spa", "Japanese-inspired day spa, Old Mill District"),
                ("Juniper Swim & Fitness", "Community pool and gym, lap swimming and classes"),
            ],
        },
    },
}


def _jitter_coord(center: tuple[float, float], radius_km: float = 8.0) -> tuple[float, float]:
    """Add random offset to center coordinates within radius."""
    lat_offset = random.uniform(-radius_km / 111, radius_km / 111)
    lng_offset = random.uniform(-radius_km / 111, radius_km / 111)
    return (center[0] + lat_offset, center[1] + lng_offset)


async def seed_city_nodes(
    pool: asyncpg.Pool,
    city_name: str,
) -> dict[str, int]:
    """Seed synthetic ActivityNodes for a city. Idempotent via ON CONFLICT."""
    city_data = CITIES.get(city_name)
    if not city_data:
        raise ValueError(f"Unknown city: {city_name}. Available: {list(CITIES.keys())}")

    counts: dict[str, int] = {"inserted": 0, "skipped": 0}
    now = datetime.utcnow()

    async with pool.acquire() as conn:
        async with conn.transaction():
            for category, nodes in city_data["nodes"].items():
                for name, description in nodes:
                    clean_name = name.lower().replace(" ", "-").replace("'", "")
                    clean_city = city_name.lower().replace(" ", "-")
                    slug = f"{clean_name}-{clean_city}"
                    lat, lng = _jitter_coord(city_data["center"])
                    neighborhood = random.choice(city_data["neighborhoods"])

                    # Price level heuristic by category
                    price_map = {
                        "dining": random.choice([1, 2, 2, 3]),
                        "drinks": random.choice([2, 2, 3]),
                        "culture": random.choice([1, 1, 2]),
                        "outdoors": 1,
                        "active": random.choice([1, 2, 3]),
                        "entertainment": random.choice([2, 3, 3]),
                        "shopping": random.choice([1, 2, 3]),
                        "experience": random.choice([1, 2, 2]),
                        "nightlife": random.choice([2, 2, 3]),
                        "group_activity": random.choice([2, 2, 3]),
                        "wellness": random.choice([2, 3, 3, 4]),
                    }

                    result = await conn.execute(
                        """
                        INSERT INTO activity_nodes (
                            "id", "name", "slug", "canonicalName",
                            "city", "country", "neighborhood",
                            "latitude", "longitude",
                            "category", "priceLevel",
                            "sourceCount", "convergenceScore", "authorityScore",
                            "descriptionShort",
                            "status", "isCanonical",
                            "lastScrapedAt", "lastValidatedAt",
                            "createdAt", "updatedAt"
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                            $12, $13, $14, $15, $16, $17, $18, $18, $18, $18
                        )
                        ON CONFLICT ("slug") DO NOTHING
                        """,
                        str(uuid.uuid4()),
                        name,
                        slug,
                        name.lower(),
                        city_name,
                        city_data["country"],
                        neighborhood,
                        lat,
                        lng,
                        category,
                        price_map.get(category, 2),
                        random.randint(2, 8),
                        round(random.uniform(0.60, 0.98), 2),
                        round(random.uniform(0.55, 0.95), 2),
                        description,
                        "approved",
                        True,
                        now,
                    )

                    if result == "INSERT 0 1":
                        counts["inserted"] += 1
                    else:
                        counts["skipped"] += 1

    return counts


async def main():
    """Seed all configured cities."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    url = os.environ.get("DATABASE_URL")
    if not url:
        logger.error("DATABASE_URL not set")
        return

    pool = await asyncpg.create_pool(url)
    try:
        for city_name in CITIES:
            logger.info(f"Seeding {city_name}...")
            counts = await seed_city_nodes(pool, city_name)
            logger.info(f"  {city_name}: {counts['inserted']} inserted, {counts['skipped']} skipped")

        # Summary
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT "city", COUNT(*) as cnt FROM activity_nodes GROUP BY "city" ORDER BY "city"'
            )
            logger.info("Final node counts:")
            for r in rows:
                cats = await conn.fetch(
                    'SELECT "category", COUNT(*) as cnt FROM activity_nodes WHERE "city" = $1 GROUP BY "category" ORDER BY cnt DESC',
                    r["city"],
                )
                cat_str = ", ".join(f'{c["category"]}={c["cnt"]}' for c in cats)
                logger.info(f"  {r['city']}: {r['cnt']} total ({cat_str})")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
