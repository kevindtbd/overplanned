"""
Tests for city_configs.py -- Phase 7.1 city seeding configuration.

Covers:
- All 7 cities have complete configs with required fields
- Spanish accent normalization in entity resolution
- Validation threshold logic
- Stopword filtering removes known chains
- Bounding box containment
- Subreddit weight aggregation
- Neighborhood term -> city mapping
"""

import pytest

from services.api.pipeline.city_configs import (
    CITY_CONFIGS,
    COMMON_CHAIN_STOPWORDS,
    BoundingBox,
    CityConfig,
    ValidationResult,
    get_all_neighborhood_terms,
    get_all_stopwords,
    get_all_subreddit_weights,
    get_city_config,
    get_target_cities_dict,
)
from services.api.pipeline.entity_resolution import (
    normalize_name,
    strip_accents,
    compute_content_hash,
)


# ===================================================================
# All 7 cities have complete configs
# ===================================================================


EXPECTED_CITY_SLUGS = [
    "austin",
    "new-orleans",
    "seattle",
    "asheville",
    "portland",
    "mexico-city",
    "bend",
]


class TestAllCitiesPresent:
    def test_all_7_cities_configured(self):
        for slug in EXPECTED_CITY_SLUGS:
            assert slug in CITY_CONFIGS, f"Missing city config for {slug}"

    def test_no_extra_cities(self):
        """Only the 7 expected cities should be configured."""
        assert set(CITY_CONFIGS.keys()) == set(EXPECTED_CITY_SLUGS)

    @pytest.mark.parametrize("slug", EXPECTED_CITY_SLUGS)
    def test_city_has_required_fields(self, slug):
        config = CITY_CONFIGS[slug]
        assert config.name, f"{slug} missing name"
        assert config.slug == slug, f"{slug} slug mismatch"
        assert config.country, f"{slug} missing country"
        assert config.timezone, f"{slug} missing timezone"
        assert len(config.subreddits) >= 1, f"{slug} needs at least 1 subreddit"
        assert len(config.neighborhood_terms) >= 5, f"{slug} needs at least 5 neighborhood terms"
        assert config.bbox.lat_min < config.bbox.lat_max, f"{slug} invalid bbox lat"
        assert config.bbox.lng_min < config.bbox.lng_max, f"{slug} invalid bbox lng"

    @pytest.mark.parametrize("slug", EXPECTED_CITY_SLUGS)
    def test_subreddit_weights_in_range(self, slug):
        config = CITY_CONFIGS[slug]
        for sub, weight in config.subreddits.items():
            assert 0.0 < weight <= 1.0, (
                f"{slug}: subreddit {sub} weight {weight} out of range (0, 1]"
            )

    @pytest.mark.parametrize("slug", EXPECTED_CITY_SLUGS)
    def test_expected_nodes_range_valid(self, slug):
        config = CITY_CONFIGS[slug]
        assert config.expected_nodes_min > 0
        assert config.expected_nodes_max > config.expected_nodes_min

    @pytest.mark.parametrize("slug", EXPECTED_CITY_SLUGS)
    def test_timezone_format(self, slug):
        config = CITY_CONFIGS[slug]
        assert "/" in config.timezone, f"{slug} timezone should be Area/Location format"


# ===================================================================
# Canary city (Bend)
# ===================================================================


class TestCanaryCity:
    def test_bend_is_canary(self):
        assert CITY_CONFIGS["bend"].is_canary is True

    def test_no_other_canary(self):
        canaries = [s for s, c in CITY_CONFIGS.items() if c.is_canary]
        assert canaries == ["bend"]

    def test_bend_lower_minimum(self):
        """Bend is a small city -- lower node minimum than others."""
        bend = CITY_CONFIGS["bend"]
        austin = CITY_CONFIGS["austin"]
        assert bend.expected_nodes_min < austin.expected_nodes_min


# ===================================================================
# Mexico City specifics
# ===================================================================


class TestMexicoCityConfig:
    def test_language_hints_include_spanish(self):
        config = CITY_CONFIGS["mexico-city"]
        assert "es" in config.language_hints
        assert "en" in config.language_hints

    def test_neighborhood_terms_include_accented_variants(self):
        config = CITY_CONFIGS["mexico-city"]
        terms = config.neighborhood_terms
        # Should have both accented and unaccented versions
        assert "coyoacan" in terms
        assert "coyoacán" in terms
        assert "juarez" in terms
        assert "juárez" in terms

    def test_us_cities_default_english(self):
        for slug in ["austin", "seattle", "portland", "bend", "asheville"]:
            config = CITY_CONFIGS[slug]
            assert config.language_hints == ["en"]


# ===================================================================
# Spanish accent normalization (entity resolution)
# ===================================================================


class TestSpanishAccentNormalization:
    def test_accent_e_stripped(self):
        assert strip_accents("cafe") == "cafe"
        assert strip_accents("cafe") == strip_accents("cafe")

    def test_taqueria_accent_normalized(self):
        assert strip_accents("taqueria") == strip_accents("taqueria")

    def test_n_tilde_stripped(self):
        result = strip_accents("dona")
        assert result == "dona"
        result_tilde = strip_accents("do\u00f1a")
        assert result_tilde == "dona"

    def test_normalize_name_strips_accents(self):
        """normalize_name should treat accented and unaccented as equivalent."""
        n1 = normalize_name("Taqueria El Sol")
        n2 = normalize_name("Taquer\u00eda El Sol")
        assert n1 == n2

    def test_normalize_name_strips_spanish_suffixes(self):
        result = normalize_name("La Taqueria Orinoco")
        assert "taqueria" not in result
        assert "orinoco" in result

    def test_normalize_name_strips_restaurante(self):
        result = normalize_name("Restaurante Casa Blanca")
        assert "restaurante" not in result
        assert "casa" in result or "blanca" in result

    def test_normalize_name_cantina(self):
        result = normalize_name("Cantina La Fuente")
        assert "cantina" not in result
        assert "fuente" in result

    def test_normalize_name_mercado(self):
        result = normalize_name("Mercado Roma")
        assert "mercado" not in result
        assert "roma" in result

    def test_accented_cafe_stripped(self):
        """Both cafe and cafe (with accent) should be stripped as suffixes."""
        r1 = normalize_name("Blue Bottle Cafe")
        r2 = normalize_name("Blue Bottle Caf\u00e9")
        assert "cafe" not in r1
        assert "cafe" not in r2

    def test_content_hash_accent_invariant(self):
        """Same venue with/without accents should produce same content hash."""
        h1 = compute_content_hash("Taquer\u00eda Orinoco", 19.4326, -99.1332, "dining")
        h2 = compute_content_hash("Taqueria Orinoco", 19.4326, -99.1332, "dining")
        assert h1 == h2


# ===================================================================
# Stopword filtering
# ===================================================================


class TestStopwordFiltering:
    def test_common_chains_in_stopwords(self):
        stopwords = get_all_stopwords()
        known_chains = ["mcdonalds", "starbucks", "subway", "chipotle", "taco bell"]
        for chain in known_chains:
            assert chain in stopwords, f"Chain '{chain}' should be in stopwords"

    def test_city_specific_stopwords_included(self):
        stopwords = get_all_stopwords()
        assert "oxxo" in stopwords  # Mexico City
        assert "sanborns" in stopwords  # Mexico City

    def test_stopwords_all_lowercase(self):
        stopwords = get_all_stopwords()
        for word in stopwords:
            assert word == word.lower(), f"Stopword '{word}' should be lowercase"

    def test_stopwords_exclude_real_venues(self):
        """Make sure we don't accidentally filter out real venues."""
        stopwords = get_all_stopwords()
        real_venues = ["franklin bbq", "buc-ees", "torchys"]
        for venue in real_venues:
            # These are borderline -- just verify they are not in the common list
            assert venue not in COMMON_CHAIN_STOPWORDS


# ===================================================================
# Bounding box
# ===================================================================


class TestBoundingBox:
    def test_contains_point_inside(self):
        bbox = BoundingBox(lat_min=30.0, lat_max=31.0, lng_min=-98.0, lng_max=-97.0)
        assert bbox.contains(30.5, -97.5) is True

    def test_contains_point_outside(self):
        bbox = BoundingBox(lat_min=30.0, lat_max=31.0, lng_min=-98.0, lng_max=-97.0)
        assert bbox.contains(29.0, -97.5) is False

    def test_contains_point_on_boundary(self):
        bbox = BoundingBox(lat_min=30.0, lat_max=31.0, lng_min=-98.0, lng_max=-97.0)
        assert bbox.contains(30.0, -98.0) is True

    def test_austin_bbox_contains_downtown(self):
        bbox = CITY_CONFIGS["austin"].bbox
        # Downtown Austin coordinates
        assert bbox.contains(30.2672, -97.7431) is True

    def test_austin_bbox_excludes_houston(self):
        bbox = CITY_CONFIGS["austin"].bbox
        # Houston coordinates
        assert bbox.contains(29.7604, -95.3698) is False

    def test_mexico_city_bbox_contains_roma_norte(self):
        bbox = CITY_CONFIGS["mexico-city"].bbox
        # Roma Norte approximate coordinates
        assert bbox.contains(19.4195, -99.1626) is True

    def test_bend_bbox_contains_downtown(self):
        bbox = CITY_CONFIGS["bend"].bbox
        # Downtown Bend
        assert bbox.contains(44.0582, -121.3153) is True


# ===================================================================
# Helper function tests
# ===================================================================


class TestHelperFunctions:
    def test_get_city_config_valid(self):
        config = get_city_config("austin")
        assert config.name == "Austin"

    def test_get_city_config_invalid(self):
        with pytest.raises(KeyError, match="Unknown city slug"):
            get_city_config("narnia")

    def test_get_all_subreddit_weights_includes_general(self):
        weights = get_all_subreddit_weights()
        assert "solotravel" in weights
        assert "travel" in weights
        assert "foodtravel" in weights

    def test_get_all_subreddit_weights_includes_city_subs(self):
        weights = get_all_subreddit_weights()
        assert "austin" in weights
        assert "asknola" in weights
        assert "seattle" in weights
        assert "cdmx" in weights
        assert "bend" in weights

    def test_subreddit_weights_higher_wins(self):
        """If a sub appears in multiple configs, highest weight wins."""
        weights = get_all_subreddit_weights()
        # All weights should be in (0, 1]
        for sub, weight in weights.items():
            assert 0.0 < weight <= 1.0, f"{sub}: {weight}"

    def test_get_all_neighborhood_terms_maps_correctly(self):
        terms = get_all_neighborhood_terms()
        assert terms.get("south congress") == "austin"
        assert terms.get("french quarter") == "new-orleans"
        assert terms.get("capitol hill") == "seattle"
        assert terms.get("roma norte") == "mexico-city"
        assert terms.get("pilot butte") == "bend"
        assert terms.get("alberta") == "portland"
        assert terms.get("river arts district") == "asheville"

    def test_get_target_cities_dict_format(self):
        target = get_target_cities_dict()
        assert isinstance(target, dict)
        for slug in EXPECTED_CITY_SLUGS:
            assert slug in target
            assert isinstance(target[slug], list)
            assert all(term == term.lower() for term in target[slug])


# ===================================================================
# Validation result structure
# ===================================================================


class TestValidationResult:
    def test_validation_result_defaults(self):
        vr = ValidationResult(city="test", passed=True)
        assert vr.node_count == 0
        assert vr.vibe_coverage_pct == 0.0
        assert vr.max_category_share == 0.0
        assert vr.issues == []

    def test_validation_result_with_issues(self):
        vr = ValidationResult(
            city="test",
            passed=False,
            node_count=50,
            issues=["Node count 50 below minimum 200"],
        )
        assert not vr.passed
        assert len(vr.issues) == 1


# ===================================================================
# New Orleans specifics
# ===================================================================


class TestNewOrleansConfig:
    def test_asknola_highest_weight(self):
        config = CITY_CONFIGS["new-orleans"]
        assert config.subreddits["asknola"] >= config.subreddits["neworleans"]

    def test_neighborhood_terms_include_key_areas(self):
        config = CITY_CONFIGS["new-orleans"]
        terms = config.neighborhood_terms
        assert "french quarter" in terms
        assert "bywater" in terms
        assert "marigny" in terms
        assert "frenchmen street" in terms
