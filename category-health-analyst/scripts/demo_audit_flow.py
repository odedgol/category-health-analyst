"""Run a local end-to-end demo of catalogs, QuerySpec, DuckDB, and auditing."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
from category_health.audit import AuditTrail, InMemoryAuditSink
from category_health.catalogs.catalogs import load_metric_catalog, load_site_catalog
from category_health.catalogs.categories import load_category_catalog
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.domain.query import AnalyticsQuerySpec, QueryIntent
from category_health.repositories.duckdb import DuckDbMetricsRepository


def main() -> None:
    project_root = Path(__file__).parents[1]
    sink = InMemoryAuditSink()
    audit = AuditTrail(sink)

    with audit.step(
        "resolve_category",
        {"mention": "Antiques"},
        {"mention": "Antiques"},
    ) as step:
        catalog = load_category_catalog(project_root / "data" / "categories_source.txt")
        category = catalog.resolve("Antiques")
        if category is None:
            raise ValueError("Antiques did not resolve")
        step.set_output({"category_id": category.category_id, "name": category.name})
        step.set_output_object(category)

    with audit.step(
        "resolve_site",
        {"mention": "Deutschland"},
        {"mention": "Deutschland"},
    ) as step:
        site_catalog = load_site_catalog(project_root / "data" / "sites.yaml")
        site = site_catalog.resolve("Deutschland")
        if site is None:
            raise ValueError("Deutschland did not resolve")
        step.set_output({"site_id": site.site_id, "name": site.name})
        step.set_output_object(site)

    with audit.step(
        "resolve_metric",
        {"mention": "image coverage"},
        {"mention": "image coverage"},
    ) as step:
        metric_catalog = load_metric_catalog(project_root / "data" / "metrics.yaml")
        metric = metric_catalog.resolve("image coverage")
        if metric is None:
            raise ValueError("image coverage did not resolve")
        step.set_output({"metric_id": metric.metric_id})
        step.set_output_object(metric)

    with audit.step("build_query") as step:
        query = AnalyticsQuerySpec(
            intent=QueryIntent.TREND,
            metric_ids=(metric.metric_id,),
            category_id=category.category_id,
            site_ids=(site.site_id,),
            date_range=DateRange(start=date(2026, 9, 9), end=date(2026, 9, 10)),
            confidence=0.99,
        )
        step.set_output({"is_executable": query.is_executable})
        step.set_output_object(query)

    repository = DuckDbMetricsRepository(duckdb.connect(":memory:"))

    def update(day: int, hour: int, coverage: str) -> CategorySiteMetrics:
        return CategorySiteMetrics(
            category_id=category.category_id,
            site_id=site.site_id,
            observed_date=date(2026, 9, day),
            last_modified_at=datetime(2026, 9, day, hour, tzinfo=UTC),
            active_product_count=100,
            image_count=180,
            has_title=True,
            image_coverage_percentage=Decimal(coverage),
            aligned_aspects_count=450,
            misaligned_aspects_count=50,
            aligned_aspects_percentage=Decimal("90"),
            misaligned_aspects_percentage=Decimal("10"),
        )

    repository.add_update(update(9, 8, "72"))
    repository.add_update(update(10, 8, "70"))
    repository.add_update(update(10, 14, "64"))

    with audit.step(
        "retrieve_latest_per_day",
        {"category_id": category.category_id, "site_id": site.site_id},
    ) as step:
        daily = repository.latest_per_day(category.category_id, site.site_id, query.date_range)
        step.set_output({"days_returned": len(daily)})
        step.set_output_object(daily)

    print("RESULT")
    for row in daily:
        print(
            f"{row.observed_date} | LMD={row.last_modified_at.isoformat()} "
            f"| image_coverage={row.image_coverage_percentage}%"
        )

    print("\nAUDIT TRACE")
    for event in sink.for_trace(audit.trace_id):
        print(
            f"{event.sequence}. {event.step:24} {event.status.value:9} "
            f"{event.duration_ms or 0:.2f} ms"
        )
        if event.output_object is not None:
            print(json.dumps(event.output_object, indent=2, default=str))


if __name__ == "__main__":
    main()
