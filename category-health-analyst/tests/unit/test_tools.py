from datetime import date

import pytest
from category_health.application.requests import (
    AnalysisRequest,
    AnalysisRequestResolver,
    ToolResolutionError,
)
from category_health.audit import AuditTrail, InMemoryAuditSink
from category_health.catalogs.catalogs import (
    MetricCatalog,
    MetricDefinition,
    SiteCatalog,
    SiteDefinition,
)
from category_health.catalogs.categories import CategoryCatalog, CategoryDefinition


def _resolver(
    category_catalog: CategoryCatalog | None = None,
) -> tuple[AnalysisRequestResolver, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
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
        audit_sink=sink,
    )
    return resolver, sink


def test_resolver_builds_trend_query_and_audits_resolution() -> None:
    resolver, sink = _resolver()
    audit = AuditTrail(sink)

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
        ),
        audit=audit,
    )

    assert result.category_id == 100
    assert result.site_ids == (77,)
    assert result.metric_ids == ("image_coverage_percentage",)
    assert [event.step for event in sink.for_trace(audit.trace_id)] == [
        "resolve_request",
        "resolve_request",
    ]


def test_resolver_rejects_ambiguous_category() -> None:
    resolver, _ = _resolver(
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
