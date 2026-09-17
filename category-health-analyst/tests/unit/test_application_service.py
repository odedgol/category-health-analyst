from datetime import UTC, date, datetime
from decimal import Decimal

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


def test_service_is_the_deterministic_application_entry_point() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(
        CategorySiteMetrics(
            category_id=20081,
            site_id=77,
            observed_date=date(2026, 9, 10),
            last_modified_at=datetime(2026, 9, 10, 17, tzinfo=UTC),
            active_product_count=100,
            image_coverage_percentage=Decimal("64"),
            image_count=180,
            has_title=True,
            aligned_aspects_count=450,
            misaligned_aspects_count=50,
            aligned_aspects_percentage=Decimal("90"),
            misaligned_aspects_percentage=Decimal("10"),
        )
    )
    sink = InMemoryAuditSink()
    service = CategoryHealthService(
        repository=repository,
        category_catalog=CategoryCatalog((CategoryDefinition(20081, "Antiques"),)),
        site_catalog=SiteCatalog(
            (SiteDefinition(77, "Germany", "Germany", "DE", ()),)
        ),
        metric_catalog=MetricCatalog(
            (
                MetricDefinition(
                    "image_coverage_percentage",
                    "Image coverage percentage",
                    "percentage",
                    ("image coverage",),
                ),
            )
        ),
        audit_sink=sink,
    )

    response = service.analyze(
        {
            "intent": "snapshot",
            "category": "Antiques",
            "sites": ["Germany"],
            "metrics": ["image coverage"],
        }
    )

    assert response["status"] == "ok"
    assert response["category_id"] == 20081
    assert response["values"][0]["value"] == "64"
    assert response["values"][0]["metric_id"] == "image_coverage_percentage"
    assert service.list_metrics()["metrics"][0]["metric_id"] == (
        "image_coverage_percentage"
    )
