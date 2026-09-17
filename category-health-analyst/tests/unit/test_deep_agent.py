from datetime import UTC, date, datetime
from decimal import Decimal

from category_health.agent.deep_agent import (
    create_analysis_tool,
    create_metric_catalog_tool,
)
from category_health.application.service import CategoryHealthService
from category_health.audit import InMemoryAuditSink
from category_health.catalogs.catalogs import (
    MetricCatalog,
    MetricDefinition,
    SiteCatalog,
    SiteDefinition,
)
from category_health.catalogs.categories import CategoryCatalog, CategoryDefinition
from category_health.domain.models import CategorySiteMetrics
from category_health.repositories.in_memory import InMemoryMetricsRepository


def test_deep_agent_domain_tool_runs_without_an_external_model() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(
        CategorySiteMetrics(
            category_id=100,
            site_id=77,
            observed_date=date(2026, 9, 9),
            last_modified_at=datetime(2026, 9, 9, 17, tzinfo=UTC),
            active_product_count=10,
            image_coverage_percentage=Decimal("72"),
            image_count=18,
            has_title=True,
            aligned_aspects_count=9,
            misaligned_aspects_count=1,
            aligned_aspects_percentage=Decimal("90"),
            misaligned_aspects_percentage=Decimal("10"),
        )
    )
    sink = InMemoryAuditSink()
    service = CategoryHealthService(
        repository=repository,
        category_catalog=CategoryCatalog((CategoryDefinition(100, "Armor"),)),
        site_catalog=SiteCatalog((SiteDefinition(77, "Germany", "Germany", "DE", ()),)),
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
    tool = create_analysis_tool(service, sink)

    response = tool(
        intent="trend",
        category="Armor",
        sites=["Germany"],
        metrics=["image coverage"],
        start_date="2026-09-09",
        end_date="2026-09-09",
    )

    assert response["intent"] == "trend"
    assert response["values"][0]["metric_id"] == "image_coverage_percentage"
    assert response["values"][0]["value"] == "72"

    unknown_metric = tool(
        intent="trend",
        category="Armor",
        sites=["Germany"],
        metrics=["quality score"],
        start_date="2026-09-09",
        end_date="2026-09-09",
    )
    assert unknown_metric["status"] == "needs_clarification"
    assert [
        metric["metric_id"] for metric in unknown_metric["available_metrics"]
    ] == ["image_coverage_percentage"]


def test_metric_catalog_tool_returns_every_supported_option_and_audits_it() -> None:
    sink = InMemoryAuditSink()
    catalog = MetricCatalog(
        (
            MetricDefinition(
                "image_count",
                "Image count",
                "count",
                ("number of images", "total images"),
            ),
            MetricDefinition("has_title", "Has title", "boolean", ("title exists",)),
        )
    )

    service = CategoryHealthService(
        repository=InMemoryMetricsRepository(),
        category_catalog=CategoryCatalog((CategoryDefinition(100, "Armor"),)),
        site_catalog=SiteCatalog(
            (SiteDefinition(77, "Germany", "Germany", "DE", ()),)
        ),
        metric_catalog=catalog,
        audit_sink=sink,
    )

    response = create_metric_catalog_tool(service, sink)()

    assert response["status"] == "ok"
    assert [metric["metric_id"] for metric in response["metrics"]] == [
        "image_count",
        "has_title",
    ]
    assert response["metrics"][0]["accepted_names"] == [
        "Image count",
        "image_count",
        "number of images",
        "total images",
    ]
    event = next(
        event
        for event in sink.events
        if event.step == "list_available_metrics" and event.status.value == "succeeded"
    )
    assert event.output_summary == {"metric_count": 2, "source": "metric_catalog"}
