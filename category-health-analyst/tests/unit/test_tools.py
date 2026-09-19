from datetime import date

import pytest
from category_health.application.requests import (
    AnalysisRequest,
    AnalysisRequestResolver,
    ToolResolutionError,
)
from category_health.catalogs.catalogs import (
    MetricCatalog,
    MetricDefinition,
    SiteCatalog,
    SiteDefinition,
)
from category_health.catalogs.categories import CategoryCatalog, CategoryDefinition


def _resolver(
    category_catalog: CategoryCatalog | None = None,
) -> AnalysisRequestResolver:
    resolver = AnalysisRequestResolver(
        category_catalog=category_catalog
        or CategoryCatalog(
            (
                CategoryDefinition(category_id=100, name="Armor"),
                CategoryDefinition(category_id=200, name="Books"),
            )
        ),
        site_catalog=SiteCatalog(
            (SiteDefinition(77, "Germany", "Germany", "DE", ("Deutschland",)),)
        ),
        metric_catalog=MetricCatalog(
            (
                MetricDefinition(
                    "image_coverage_percentage",
                    "Image coverage percentage",
                    "%",
                    ("image coverage",),
                ),
            )
        ),
    )
    return resolver


def test_resolver_builds_canonical_trend_query() -> None:
    resolver = _resolver()

    result = resolver.resolve(
        AnalysisRequest.model_validate(
            {
                "intent": "trend",
                "category": "Armor",
                "sites": ["Deutschland"],
                "metrics": ["image coverage"],
                "start_date": date(2026, 9, 1),
                "end_date": date(2026, 9, 7),
            }
        )
    )

    assert result.category_id == 100
    assert result.site_ids == (77,)
    assert result.metric_ids == ("image_coverage_percentage",)


def test_resolver_rejects_ambiguous_category() -> None:
    resolver = _resolver(
        CategoryCatalog(
            (
                CategoryDefinition(category_id=100, name="Armor"),
                CategoryDefinition(category_id=101, name="Armor"),
            )
        )
    )

    with pytest.raises(ToolResolutionError, match="ambiguous") as error:
        resolver.resolve(
            AnalysisRequest.model_validate(
                {
                    "intent": "trend",
                    "category": "Armor",
                    "sites": ["Germany"],
                    "metrics": ["image coverage"],
                    "start_date": "2026-09-01",
                    "end_date": "2026-09-07",
                }
            )
        )

    assert error.value.unresolved_fields == ("category",)


def test_resolver_rejects_unexpected_arguments() -> None:
    with pytest.raises(ValueError, match="unexpected"):
        AnalysisRequest.model_validate(
            {
                "intent": "snapshot",
                "category": "Armor",
                "sites": ["Germany"],
                "metrics": ["image coverage"],
                "unexpected": True,
            }
        )
