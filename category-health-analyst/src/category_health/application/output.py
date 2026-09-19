"""Response models and atomic metric comparison rules."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from category_health.domain.models import CategorySiteMetrics


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


def validate_metric_ids(metric_ids: tuple[str, ...]) -> None:
    """Reject fields that are not part of the supported metric contract."""

    for metric_id in metric_ids:
        if metric_id not in METRIC_UNITS:
            raise ValueError(f"Unknown metric field: {metric_id}")
