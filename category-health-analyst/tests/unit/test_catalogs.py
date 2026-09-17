from pathlib import Path

import pytest
from category_health.catalogs.catalogs import (
    MetricCatalog,
    MetricDefinition,
    SiteCatalog,
    SiteDefinition,
    load_metric_catalog,
    load_site_catalog,
)

ROOT = Path(__file__).parents[2]


def test_site_aliases_resolve_to_the_official_site_id() -> None:
    catalog = load_site_catalog(ROOT / "data" / "sites.yaml")

    assert catalog.resolve("Germany").site_id == 77
    assert catalog.resolve("Deutschland").site_id == 77
    assert catalog.resolve("DE").site_id == 77
    assert catalog.resolve("ebay.de").site_id == 77
    assert catalog.resolve("77").site_id == 77


def test_unknown_site_does_not_default_to_us() -> None:
    catalog = load_site_catalog(ROOT / "data" / "sites.yaml")

    assert catalog.resolve("Europe") is None


def test_metric_aliases_resolve_to_metric_ids() -> None:
    catalog = load_metric_catalog(ROOT / "data" / "metrics.yaml")

    assert catalog.resolve("image percentage").metric_id == "image_coverage_percentage"
    assert catalog.resolve("taxonomy mismatch").metric_id == "misaligned_aspects_count"
    assert catalog.resolve("has a title").metric_id == "has_title"


def test_unknown_metric_has_no_match() -> None:
    catalog = load_metric_catalog(ROOT / "data" / "metrics.yaml")

    assert catalog.resolve("quality score") is None


def test_metric_resolution_ignores_only_safe_query_qualifiers() -> None:
    catalog = load_metric_catalog(ROOT / "data" / "metrics.yaml")

    assert catalog.resolve("daily image count").metric_id == "image_count"
    assert (
        catalog.resolve("latest daily image coverage trend").metric_id
        == "image_coverage_percentage"
    )
    assert catalog.resolve("daily_image_coverage").metric_id == "image_coverage_percentage"
    assert catalog.resolve("daily quality score trend") is None


def test_duplicate_site_aliases_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate site alias"):
        SiteCatalog(
            (
                SiteDefinition(1, "One", "One", "O1", ("shared",)),
                SiteDefinition(2, "Two", "Two", "O2", ("shared",)),
            )
        )


def test_duplicate_metric_aliases_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate metric alias"):
        MetricCatalog(
            (
                MetricDefinition("first", "First", "count", ("shared",)),
                MetricDefinition("second", "Second", "count", ("shared",)),
            )
        )
