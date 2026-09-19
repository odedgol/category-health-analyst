"""Execute the five category-health analyses directly from a resolved query."""

from datetime import timedelta
from itertools import pairwise

from category_health.application.output import (
    AnalysisResponse,
    ExposedMetricValue,
    compare_observations,
    validate_metric_ids,
)
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.domain.ports import MetricsRepository
from category_health.domain.query import AnalysisQuery, QueryIntent

ObservationPair = tuple[CategorySiteMetrics, CategorySiteMetrics, str]


class CategoryHealthAnalyzer:
    """Run one resolved query without a separate planner or execution engine."""

    def __init__(self, repository: MetricsRepository) -> None:
        self._repository = repository

    def analyze(
        self,
        query: AnalysisQuery,
    ) -> AnalysisResponse:
        """Choose the requested analysis and return its complete response."""

        validate_metric_ids(query.metric_ids)
        match query.intent:
            case QueryIntent.SNAPSHOT:
                return self._snapshot(query)
            case QueryIntent.TREND:
                return self._trend(query)
            case QueryIntent.COMPARE_PERIODS:
                return self._compare_periods(query)
            case QueryIntent.COMPARE_SITES:
                return self._compare_sites(query)
            case QueryIntent.EXPLAIN_CHANGE:
                return self._explain_change(query)

    def _snapshot(
        self,
        query: AnalysisQuery,
    ) -> AnalysisResponse:
        values: list[ExposedMetricValue] = []
        warnings: list[str] = []

        for site_id in query.site_ids:
            observation = self._latest_snapshot(query, site_id)
            if observation is None:
                warnings.extend(self._no_data_warnings(query.category_id, site_id, "snapshot"))
                continue
            values.extend(self._metric_values(observation, "snapshot", query.metric_ids))

        return self._response(query, values, [], warnings)

    def _trend(
        self,
        query: AnalysisQuery,
    ) -> AnalysisResponse:
        assert query.date_range is not None
        values: list[ExposedMetricValue] = []
        pairs: list[ObservationPair] = []
        warnings: list[str] = []

        for site_id in query.site_ids:
            rows = self._daily_rows(query.category_id, site_id, query.date_range)
            values.extend(self._values_for_rows(rows, "current", query.metric_ids))
            warnings.extend(self._time_series_warnings(query, site_id, "current", rows))
            pairs.extend(
                (previous, current, "consecutive_observations")
                for previous, current in pairwise(rows)
            )

        return self._response(query, values, pairs, warnings)

    def _explain_change(
        self,
        query: AnalysisQuery,
    ) -> AnalysisResponse:
        assert query.date_range is not None
        values: list[ExposedMetricValue] = []
        pairs: list[ObservationPair] = []
        warnings: list[str] = []

        for site_id in query.site_ids:
            rows = self._daily_rows(query.category_id, site_id, query.date_range)
            values.extend(self._values_for_rows(rows, "current", query.metric_ids))
            warnings.extend(self._time_series_warnings(query, site_id, "current", rows))
            if len(rows) >= 2:
                pairs.append((rows[0], rows[-1], "first_to_last_observation"))

        warnings.append("Observed metric changes do not establish causes.")
        return self._response(query, values, pairs, warnings)

    def _compare_periods(
        self,
        query: AnalysisQuery,
    ) -> AnalysisResponse:
        assert query.date_range is not None
        assert query.comparison_range is not None
        values: list[ExposedMetricValue] = []
        pairs: list[ObservationPair] = []
        warnings: list[str] = []

        for site_id in query.site_ids:
            previous = self._daily_rows(
                query.category_id,
                site_id,
                query.comparison_range,
            )
            current = self._daily_rows(query.category_id, site_id, query.date_range)
            values.extend(self._values_for_rows(previous, "comparison", query.metric_ids))
            values.extend(self._values_for_rows(current, "current", query.metric_ids))
            warnings.extend(
                self._period_warnings(
                    query.category_id,
                    site_id,
                    "comparison",
                    previous,
                    query.comparison_range,
                )
            )
            warnings.extend(
                self._period_warnings(
                    query.category_id,
                    site_id,
                    "current",
                    current,
                    query.date_range,
                )
            )
            if previous and current:
                pairs.append((previous[-1], current[-1], "latest_snapshot_per_period"))
            else:
                warnings.append(f"Site {site_id}: both periods need data for comparison.")

        return self._response(query, values, pairs, warnings)

    def _compare_sites(
        self,
        query: AnalysisQuery,
    ) -> AnalysisResponse:
        first_site, second_site = query.site_ids
        first_rows = self._site_comparison_rows(query, first_site)
        second_rows = self._site_comparison_rows(query, second_site)
        period = "current" if query.date_range else "snapshot"

        values = [
            *self._values_for_rows(first_rows, period, query.metric_ids),
            *self._values_for_rows(second_rows, period, query.metric_ids),
        ]
        warnings: list[str] = []
        if query.date_range is not None:
            warnings.extend(
                self._period_warnings(
                    query.category_id,
                    first_site,
                    period,
                    first_rows,
                    query.date_range,
                )
            )
            warnings.extend(
                self._period_warnings(
                    query.category_id,
                    second_site,
                    period,
                    second_rows,
                    query.date_range,
                )
            )
        else:
            if not first_rows:
                warnings.extend(
                    self._no_data_warnings(query.category_id, first_site, period)
                )
            if not second_rows:
                warnings.extend(
                    self._no_data_warnings(query.category_id, second_site, period)
                )

        first_by_date = {row.observed_date: row for row in first_rows}
        second_by_date = {row.observed_date: row for row in second_rows}
        common_dates = sorted(first_by_date.keys() & second_by_date.keys())
        pairs = [
            (first_by_date[day], second_by_date[day], "same_day_sites")
            for day in common_dates
        ]
        if first_by_date.keys() != second_by_date.keys() or not common_dates:
            warnings.append(
                "Site comparison uses matching dates only; unmatched dates are omitted."
            )

        return self._response(query, values, pairs, warnings)

    def _site_comparison_rows(
        self,
        query: AnalysisQuery,
        site_id: int,
    ) -> list[CategorySiteMetrics]:
        if query.date_range is not None:
            return self._daily_rows(query.category_id, site_id, query.date_range)
        observation = self._repository.latest_update(query.category_id, site_id)
        return [] if observation is None else [observation]

    def _latest_snapshot(
        self,
        query: AnalysisQuery,
        site_id: int,
    ) -> CategorySiteMetrics | None:
        if query.date_range is None:
            return self._repository.latest_update(query.category_id, site_id)
        rows = self._daily_rows(query.category_id, site_id, query.date_range)
        return rows[-1] if rows else None

    def _daily_rows(
        self,
        category_id: int,
        site_id: int,
        date_range: DateRange,
    ) -> list[CategorySiteMetrics]:
        return self._repository.latest_per_day(category_id, site_id, date_range)

    @staticmethod
    def _metric_values(
        row: CategorySiteMetrics,
        period: str,
        metric_ids: tuple[str, ...],
    ) -> list[ExposedMetricValue]:
        return [
            ExposedMetricValue(
                site_id=row.site_id,
                period=period,
                observed_date=row.observed_date,
                last_modified_at=row.last_modified_at,
                metric_id=metric_id,
                value=getattr(row, metric_id),
            )
            for metric_id in metric_ids
        ]

    def _values_for_rows(
        self,
        rows: list[CategorySiteMetrics],
        period: str,
        metric_ids: tuple[str, ...],
    ) -> list[ExposedMetricValue]:
        return [
            value
            for row in rows
            for value in self._metric_values(row, period, metric_ids)
        ]

    def _time_series_warnings(
        self,
        query: AnalysisQuery,
        site_id: int,
        period: str,
        rows: list[CategorySiteMetrics],
    ) -> list[str]:
        assert query.date_range is not None
        warnings = self._period_warnings(
            query.category_id,
            site_id,
            period,
            rows,
            query.date_range,
        )
        if len(rows) < 2:
            warnings.append(f"Site {site_id}: at least two observations are needed.")
        if any(
            current.observed_date - previous.observed_date > timedelta(days=1)
            for previous, current in pairwise(rows)
        ):
            warnings.append(f"Site {site_id}: observations contain calendar gaps.")
        return warnings

    def _period_warnings(
        self,
        category_id: int,
        site_id: int,
        period: str,
        rows: list[CategorySiteMetrics],
        date_range: DateRange,
    ) -> list[str]:
        warnings: list[str] = []
        expected_days = (date_range.end - date_range.start).days + 1
        if len(rows) < expected_days:
            warnings.append(
                f"Site {site_id}, {period}: {expected_days - len(rows)} missing days; "
                "missing values are not zero."
            )
        if not rows:
            warnings.extend(self._no_data_warnings(category_id, site_id, period))
        return warnings

    def _no_data_warnings(
        self,
        category_id: int,
        site_id: int,
        period: str,
    ) -> list[str]:
        warnings = [f"No data for site {site_id}, {period}."]
        available = self._repository.available_date_range(category_id, site_id)
        if available is not None:
            warnings.append(
                f"Available dates for site {site_id}: "
                f"{available.start} through {available.end}."
            )
        return warnings

    @staticmethod
    def _response(
        query: AnalysisQuery,
        values: list[ExposedMetricValue],
        pairs: list[ObservationPair],
        warnings: list[str],
    ) -> AnalysisResponse:
        comparisons = tuple(
            compare_observations(previous, current, metric_id, method)
            for previous, current, method in pairs
            for metric_id in query.metric_ids
        )
        unique_warnings = tuple(dict.fromkeys(warnings))
        return AnalysisResponse(
            intent=query.intent.value,
            category_id=query.category_id,
            status="no_data" if not values else "partial" if unique_warnings else "ok",
            values=tuple(values),
            comparisons=comparisons,
            warnings=unique_warnings,
        )
