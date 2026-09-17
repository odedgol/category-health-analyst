"""Deterministic comparisons and focused output from complete observations."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from category_health.application.engine import AnalyticsResult, QueryResultGroup
from category_health.domain.models import CategorySiteMetrics
from category_health.domain.query import AnalyticsQuerySpec, QueryIntent


class ExposedMetricValue(BaseModel):
    site_id: int
    period: str
    observed_date: date
    last_modified_at: datetime
    metric_id: str
    value: Decimal | int | bool


class ExposedMetricComparison(BaseModel):
    site_id: int
    previous_site_id: int
    metric_id: str
    method: str
    previous_date: date
    current_date: date
    previous_lmd: datetime
    current_lmd: datetime
    previous_value: Decimal | int | bool
    current_value: Decimal | int | bool
    delta: Decimal | int | None
    delta_unit: Literal["percentage_points", "count", "boolean_transition"]
    changed: bool


class AnalysisResponse(BaseModel):
    trace_id: UUID
    intent: str
    category_id: int
    status: Literal["ok", "partial", "no_data"]
    values: tuple[ExposedMetricValue, ...]
    comparisons: tuple[ExposedMetricComparison, ...] = ()
    warnings: tuple[str, ...] = ()


METRIC_UNITS = {
    "image_coverage_percentage": "percentage_points",
    "image_count": "count",
    "has_title": "boolean_transition",
    "aligned_aspects_count": "count",
    "misaligned_aspects_count": "count",
    "aligned_aspects_percentage": "percentage_points",
    "misaligned_aspects_percentage": "percentage_points",
}

ObservationPair = tuple[CategorySiteMetrics, CategorySiteMetrics, str]
ObservationGroups = dict[tuple[int, str], list[CategorySiteMetrics]]


def compare_observations(
    previous: CategorySiteMetrics,
    current: CategorySiteMetrics,
    metric_id: str,
    method: str,
) -> ExposedMetricComparison:
    """Subtract numeric snapshots; report boolean changes without subtraction."""
    unit = METRIC_UNITS[metric_id]
    before = getattr(previous, metric_id)
    after = getattr(current, metric_id)
    return ExposedMetricComparison(
        site_id=current.site_id,
        previous_site_id=previous.site_id,
        metric_id=metric_id,
        method=method,
        previous_date=previous.observed_date,
        current_date=current.observed_date,
        previous_lmd=previous.last_modified_at,
        current_lmd=current.last_modified_at,
        previous_value=before,
        current_value=after,
        delta=None if unit == "boolean_transition" else after - before,
        delta_unit=unit,
        changed=before != after,
    )


def _validate_requested_metrics(query: AnalyticsQuerySpec) -> None:
    if query.category_id is None:
        raise ValueError("An analytics result must have a category_id")
    for metric_id in query.metric_ids:
        if metric_id not in METRIC_UNITS:
            raise ValueError(f"Unknown metric field: {metric_id}")


def _exposed_values(
    group: QueryResultGroup,
    rows: list[CategorySiteMetrics],
    metric_ids: tuple[str, ...],
) -> list[ExposedMetricValue]:
    return [
        ExposedMetricValue(
            site_id=group.site_id,
            period=group.period,
            observed_date=row.observed_date,
            last_modified_at=row.last_modified_at,
            metric_id=metric_id,
            value=getattr(row, metric_id),
        )
        for row in rows
        for metric_id in metric_ids
    ]


def _inspect_group(
    query: AnalyticsQuerySpec,
    group: QueryResultGroup,
    rows: list[CategorySiteMetrics],
) -> tuple[list[str], list[ObservationPair]]:
    """Report incomplete data and select comparisons within one result group."""

    warnings: list[str] = []
    pairs: list[ObservationPair] = []
    scope = query.comparison_range if group.period == "comparison" else query.date_range
    if scope and group.period != "snapshot":
        expected = (scope.end - scope.start).days + 1
        present = {row.observed_date for row in rows}
        if len(present) < expected:
            warnings.append(
                f"Site {group.site_id}, {group.period}: {expected - len(present)} "
                "missing days; missing values are not zero."
            )
    if not rows:
        warnings.append(f"No data for site {group.site_id}, {group.period}.")
        if group.available_date_range is not None:
            warnings.append(
                f"Available dates for site {group.site_id}: "
                f"{group.available_date_range.start} through "
                f"{group.available_date_range.end}."
            )
    if query.intent == QueryIntent.TREND:
        pairs.extend((a, b, "consecutive_observations") for a, b in pairwise(rows))
    elif query.intent == QueryIntent.EXPLAIN_CHANGE and len(rows) >= 2:
        pairs.append((rows[0], rows[-1], "first_to_last_observation"))
    if query.intent in {QueryIntent.TREND, QueryIntent.EXPLAIN_CHANGE} and len(rows) < 2:
        warnings.append(f"Site {group.site_id}: at least two observations are needed.")
    if any(b.observed_date - a.observed_date > timedelta(days=1) for a, b in pairwise(rows)):
        warnings.append(f"Site {group.site_id}: observations contain calendar gaps.")
    return warnings, pairs


def _cross_group_comparisons(
    query: AnalyticsQuerySpec,
    groups: ObservationGroups,
) -> tuple[list[str], list[ObservationPair]]:
    """Select comparable observations across periods or sites."""

    warnings: list[str] = []
    pairs: list[ObservationPair] = []
    if query.intent == QueryIntent.COMPARE_PERIODS:
        for site in query.site_ids:
            before = groups.get((site, "comparison"), [])
            after = groups.get((site, "current"), [])
            if before and after:
                pairs.append((before[-1], after[-1], "latest_snapshot_per_period"))
            else:
                warnings.append(f"Site {site}: both periods need data for comparison.")
    elif query.intent == QueryIntent.COMPARE_SITES:
        period = "current" if query.date_range else "snapshot"
        before = {r.observed_date: r for r in groups.get((query.site_ids[0], period), [])}
        after = {r.observed_date: r for r in groups.get((query.site_ids[1], period), [])}
        common = before.keys() & after.keys()
        pairs.extend((before[day], after[day], "same_day_sites") for day in sorted(common))
        if before.keys() != after.keys() or not common:
            warnings.append(
                "Site comparison uses matching dates only; unmatched dates are omitted."
            )
    if query.intent == QueryIntent.EXPLAIN_CHANGE:
        warnings.append("Observed metric changes do not establish causes.")
    return warnings, pairs


def expose_requested_metrics(result: AnalyticsResult) -> AnalysisResponse:
    """Expose requested values and deterministic comparisons without filling gaps."""

    query = result.query
    _validate_requested_metrics(query)

    values: list[ExposedMetricValue] = []
    warnings: list[str] = []
    pairs: list[ObservationPair] = []
    groups: ObservationGroups = {}
    for group in result.data:
        rows = sorted(group.records, key=lambda row: row.observed_date)
        groups[group.site_id, group.period] = rows
        values.extend(_exposed_values(group, rows, query.metric_ids))
        group_warnings, group_pairs = _inspect_group(query, group, rows)
        warnings.extend(group_warnings)
        pairs.extend(group_pairs)

    cross_warnings, cross_pairs = _cross_group_comparisons(query, groups)
    warnings.extend(cross_warnings)
    pairs.extend(cross_pairs)

    comparisons = tuple(
        compare_observations(a, b, metric, method)
        for a, b, method in pairs
        for metric in query.metric_ids
    )
    return AnalysisResponse(
        trace_id=result.trace_id,
        intent=query.intent.value,
        category_id=query.category_id,
        status="no_data" if not values else "partial" if warnings else "ok",
        values=tuple(values),
        comparisons=comparisons,
        warnings=tuple(dict.fromkeys(warnings)),
    )
