from datetime import date

import pytest
from category_health.agent.tools import ToolCall, ToolRegistry, ToolResolutionError
from category_health.audit import InMemoryAuditSink
from category_health.catalogs.catalogs import (
    MetricCatalog,
    MetricDefinition,
    SiteCatalog,
    SiteDefinition,
)
from category_health.catalogs.categories import CategoryCatalog, CategoryDefinition


def _registry(
    category_catalog: CategoryCatalog | None = None,
) -> tuple[ToolRegistry, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    registry = ToolRegistry(
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
    return registry, sink


def test_registry_resolves_trend_tool_to_query_and_audits_resolution() -> None:
    registry, sink = _registry()

    result = registry.resolve(
        ToolCall(
            name="analyze_category_health",
            arguments={
                "intent": "trend",
                "category": "Armor",
                "sites": ["Deutschland"],
                "metrics": ["image coverage"],
                "start_date": date(2026, 9, 1),
                "end_date": date(2026, 9, 7),
            },
        )
    )

    assert result.query.category_id == 100
    assert result.query.site_ids == (77,)
    assert result.query.metric_ids == ("image_coverage_percentage",)
    assert result.query.is_executable
    assert [event.step for event in sink.for_trace(result.audit.trace_id)] == [
        "select_tool",
        "select_tool",
        "validate_tool_arguments",
        "validate_tool_arguments",
        "resolve_category",
        "resolve_category",
        "resolve_sites",
        "resolve_sites",
        "resolve_metrics",
        "resolve_metrics",
        "build_query",
        "build_query",
    ]


def test_registry_rejects_ambiguous_category() -> None:
    registry, _ = _registry(
        CategoryCatalog(
            (
                CategoryDefinition(category_id=100, name="Armor"),
                CategoryDefinition(category_id=101, name="Armor"),
            )
        )
    )

    with pytest.raises(ToolResolutionError, match="ambiguous") as error:
        registry.resolve(
            ToolCall(
                name="analyze_category_health",
                arguments={
                    "intent": "trend",
                    "category": "Armor",
                    "sites": ["Germany"],
                    "metrics": ["image coverage"],
                    "start_date": "2026-09-01",
                    "end_date": "2026-09-07",
                },
            )
        )

    assert error.value.unresolved_fields == ("category",)


def test_registry_rejects_unknown_tool() -> None:
    registry, _ = _registry()

    with pytest.raises(ToolResolutionError, match="Unknown tool"):
        registry.resolve(ToolCall(name="run_sql", arguments={}))
