"""In-memory repository used to prove storage behavior before adding SQL."""

from category_health.domain.models import CategorySiteMetrics, DateRange


class InMemoryMetricsRepository:
    """Store aggregate updates while preserving every distinct LMD update."""

    def __init__(self) -> None:
        self._updates: list[CategorySiteMetrics] = []

    def add_update(self, update: CategorySiteMetrics) -> None:
        identity = (
            update.category_id,
            update.site_id,
            update.observed_date,
            update.last_modified_at,
        )
        if any(
            (
                existing.category_id,
                existing.site_id,
                existing.observed_date,
                existing.last_modified_at,
            )
            == identity
            for existing in self._updates
        ):
            raise ValueError(f"Duplicate metric update: {identity}")
        self._updates.append(update)

    def list_updates(
        self, category_id: int, site_id: int, date_range: DateRange
    ) -> list[CategorySiteMetrics]:
        matching = [
            update
            for update in self._updates
            if update.category_id == category_id
            and update.site_id == site_id
            and date_range.start <= update.observed_date <= date_range.end
        ]
        return sorted(matching, key=lambda update: update.last_modified_at)

    def latest_per_day(
        self, category_id: int, site_id: int, date_range: DateRange
    ) -> list[CategorySiteMetrics]:
        latest_by_day: dict[object, CategorySiteMetrics] = {}
        for update in self.list_updates(category_id, site_id, date_range):
            current = latest_by_day.get(update.observed_date)
            if current is None or update.last_modified_at > current.last_modified_at:
                latest_by_day[update.observed_date] = update

        return [latest_by_day[day] for day in sorted(latest_by_day)]

    def latest_update(self, category_id: int, site_id: int) -> CategorySiteMetrics | None:
        matching = [
            update
            for update in self._updates
            if update.category_id == category_id and update.site_id == site_id
        ]
        return max(matching, key=lambda update: update.last_modified_at, default=None)

    def available_date_range(self, category_id: int, site_id: int) -> DateRange | None:
        dates = [
            update.observed_date
            for update in self._updates
            if update.category_id == category_id and update.site_id == site_id
        ]
        if not dates:
            return None
        return DateRange(start=min(dates), end=max(dates))
