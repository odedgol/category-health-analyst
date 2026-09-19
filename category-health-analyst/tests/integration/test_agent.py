from datetime import UTC, date, datetime
from decimal import Decimal

import duckdb
from category_health.application.analysis import CategoryHealthAnalyzer
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.domain.query import AnalysisQuery, QueryIntent
from category_health.repositories.duckdb import DuckDbMetricsRepository


def _update(day: int, hour: int, coverage: str) -> CategorySiteMetrics:
    return CategorySiteMetrics(
        category_id=20081,
        site_id=77,
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


def test_analyzer_executes_a_trend_query_without_infrastructure_concerns() -> None:
    repository = DuckDbMetricsRepository(duckdb.connect(":memory:"))
    repository.add_update(_update(9, 8, "72"))
    repository.add_update(_update(10, 8, "70"))
    repository.add_update(_update(10, 14, "64"))
    analyzer = CategoryHealthAnalyzer(repository)

    result = analyzer.analyze(
        AnalysisQuery(
            intent=QueryIntent.TREND,
            metric_ids=("image_coverage_percentage",),
            category_id=20081,
            site_ids=(77,),
            date_range=DateRange(start=date(2026, 9, 9), end=date(2026, 9, 10)),
        )
    )

    assert [value.value for value in result.values] == [
        Decimal("72.0000"),
        Decimal("64.0000"),
    ]
