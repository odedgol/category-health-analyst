from datetime import UTC, date, datetime
from decimal import Decimal

from category_health.application.requests import AnalysisRequest
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


def metric_update(day: int, image_coverage: str) -> CategorySiteMetrics:
    return CategorySiteMetrics(
        category_id=20081,
        site_id=77,
        observed_date=date(2026, 9, day),
        last_modified_at=datetime(2026, 9, day, 17, tzinfo=UTC),
        active_product_count=100,
        image_coverage_percentage=Decimal(image_coverage),
        image_count=180,
        has_title=True,
        aligned_aspects_count=450,
        misaligned_aspects_count=50,
        aligned_aspects_percentage=Decimal("90"),
        misaligned_aspects_percentage=Decimal("10"),
    )


def category_health_service(
    repository: InMemoryMetricsRepository,
) -> CategoryHealthService:
    return CategoryHealthService(
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
        audit_sink=InMemoryAuditSink(),
    )


def snapshot_request(**dates: date) -> AnalysisRequest:
    return AnalysisRequest(
        intent="snapshot",
        category="Antiques",
        sites=("Germany",),
        metrics=("image coverage",),
        **dates,
    )


def test_snapshot_returns_the_latest_observation() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(metric_update(9, "72"))
    repository.add_update(metric_update(10, "64"))
    service = category_health_service(repository)

    response = service.analyze(snapshot_request())

    assert response.status == "ok"
    assert response.category_id == 20081
    assert response.values[0].observed_date == date(2026, 9, 10)
    assert response.values[0].value == Decimal("64")
    assert response.values[0].metric_id == "image_coverage_percentage"


def test_snapshot_respects_the_requested_date_range() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(metric_update(9, "72"))
    repository.add_update(metric_update(10, "64"))
    service = category_health_service(repository)

    response = service.analyze(
        snapshot_request(
            start_date=date(2026, 9, 9),
            end_date=date(2026, 9, 9),
        )
    )

    assert response.status == "ok"
    assert response.values[0].observed_date == date(2026, 9, 9)
    assert response.values[0].value == Decimal("72")


def test_snapshot_explains_when_the_requested_range_has_no_data() -> None:
    repository = InMemoryMetricsRepository()
    repository.add_update(metric_update(10, "64"))
    service = category_health_service(repository)

    response = service.analyze(
        snapshot_request(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
        )
    )

    assert response.status == "no_data"
    assert not response.values
    assert response.warnings == (
        "No data for site 77, snapshot.",
        "Available dates for site 77: 2026-09-10 through 2026-09-10.",
    )


def test_service_lists_the_supported_metrics() -> None:
    service = category_health_service(InMemoryMetricsRepository())

    assert service.list_metrics()["metrics"][0]["metric_id"] == (
        "image_coverage_percentage"
    )
