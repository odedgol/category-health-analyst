"""Reproducible aggregate fixtures, usable with any MetricsRepository adapter."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from category_health.domain.models import CategorySiteMetrics
from category_health.domain.ports import MetricsRepository


def seed_mock_data(repository: MetricsRepository) -> None:
    """Seed 40 days, two sites and multiple updates; call on an empty repository."""
    for site in (77, 3):
        for offset in range(40):
            day = date(2026, 8, 2) + timedelta(days=offset)
            for hour in (8, 17):
                coverage = Decimal(80 - offset % 12 + (3 if site == 3 else 0))
                if day == date(2026, 9, 9) and site == 77:
                    coverage = Decimal(72)
                if day == date(2026, 9, 10) and site == 77:
                    coverage = Decimal(64)
                if hour == 8:
                    coverage += 1
                repository.add_update(
                    CategorySiteMetrics(
                        category_id=20081,
                        site_id=site,
                        observed_date=day,
                        last_modified_at=datetime.combine(day, datetime.min.time(), UTC)
                        + timedelta(hours=hour),
                        active_product_count=100,
                        image_coverage_percentage=coverage,
                        image_count=180 + offset + (10 if site == 3 else 0),
                        has_title=offset % 7 != 0,
                        aligned_aspects_count=450,
                        misaligned_aspects_count=50,
                        aligned_aspects_percentage=Decimal(90),
                        misaligned_aspects_percentage=Decimal(10),
                    )
                )
