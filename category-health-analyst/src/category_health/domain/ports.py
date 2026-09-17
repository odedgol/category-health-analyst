"""Interfaces that the application uses to access external data."""

from typing import Protocol

from category_health.domain.models import CategorySiteMetrics, DateRange


class MetricsRepository(Protocol):
    """Storage contract required by the analytics layer."""

    def add_update(self, update: CategorySiteMetrics) -> None:
        """Store one aggregate update."""

    def list_updates(
        self, category_id: int, site_id: int, date_range: DateRange
    ) -> list[CategorySiteMetrics]:
        """Return all matching updates in chronological order."""

    def latest_per_day(
        self, category_id: int, site_id: int, date_range: DateRange
    ) -> list[CategorySiteMetrics]:
        """Return one latest-LMD update for each day in the range."""

    def latest_update(self, category_id: int, site_id: int) -> CategorySiteMetrics | None:
        """Return the latest known update for a category/site pair."""

    def available_date_range(self, category_id: int, site_id: int) -> DateRange | None:
        """Return the first and last observed dates for a category/site pair."""
