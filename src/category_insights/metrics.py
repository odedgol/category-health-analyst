"""Canonical metric registry.

Every module that deals with a metric by name (the DB schema, the MCP
tools, the answer formatter) imports from here rather than hardcoding a
metric key or its trend direction. Adding a metric later means adding one
entry to `METRICS` plus one column in the DB schema — nothing else in the
codebase names an individual metric.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator


class TrendDirection(StrEnum):
    """Which direction of change counts as an improvement for a metric."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


@dataclass(frozen=True)
class MetricDefinition:
    """Describes one category-health metric."""

    key: str
    display_name: str
    unit: str  # "%" or "count"
    description: str
    trend_direction: TrendDirection


METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="product_count",
        display_name="Product count",
        unit="count",
        description=(
            "Total products in the category on that day. Drops often explain "
            "other metric dips — e.g. products moved to another category."
        ),
        trend_direction=TrendDirection.HIGHER_IS_BETTER,
    ),
    MetricDefinition(
        key="image_coverage_pct",
        display_name="Image coverage",
        unit="%",
        description="Percentage of products with at least one image.",
        trend_direction=TrendDirection.HIGHER_IS_BETTER,
    ),
    MetricDefinition(
        key="multi_image_pct",
        display_name="Multi-image coverage",
        unit="%",
        description="Percentage of products with at least two images.",
        trend_direction=TrendDirection.HIGHER_IS_BETTER,
    ),
    MetricDefinition(
        key="taxonomy_alignment_pct",
        display_name="Taxonomy alignment",
        unit="%",
        description="Percentage of products correctly mapped to a valid leaf category.",
        trend_direction=TrendDirection.HIGHER_IS_BETTER,
    ),
    MetricDefinition(
        key="attribute_completeness_pct",
        display_name="Attribute completeness",
        unit="%",
        description=(
            "Percentage of products with all required attributes populated "
            "(brand, size, color, etc.)."
        ),
        trend_direction=TrendDirection.HIGHER_IS_BETTER,
    ),
    MetricDefinition(
        key="price_anomaly_rate_pct",
        display_name="Price anomaly rate",
        unit="%",
        description="Percentage of products with a missing or outlier price vs. category median.",
        trend_direction=TrendDirection.LOWER_IS_BETTER,
    ),
    MetricDefinition(
        key="duplicate_rate_pct",
        display_name="Duplicate rate",
        unit="%",
        description="Percentage of products likely duplicated within the category.",
        trend_direction=TrendDirection.LOWER_IS_BETTER,
    ),
    MetricDefinition(
        key="orphan_rate_pct",
        display_name="Orphan rate",
        unit="%",
        description="Percentage of products with no valid leaf category at all.",
        trend_direction=TrendDirection.LOWER_IS_BETTER,
    ),
    MetricDefinition(
        key="freshness_pct",
        display_name="Freshness",
        unit="%",
        description="Percentage of products added or updated in the last 7 days.",
        trend_direction=TrendDirection.HIGHER_IS_BETTER,
    ),
)

METRICS_BY_KEY: dict[str, MetricDefinition] = {metric.key: metric for metric in METRICS}


def get_metric(metric_key: str) -> MetricDefinition:
    """Look up a metric definition by key.

    Raises:
        KeyError: if `metric_key` isn't in the registry — callers at a
            system boundary (MCP tools, the agent) are expected to turn
            this into a user-facing "unknown metric" response rather than
            let it propagate as a raw KeyError.
    """
    return METRICS_BY_KEY[metric_key]


def _validate_metric_key(value: str) -> str:
    if value not in METRICS_BY_KEY:
        valid_keys = ", ".join(sorted(METRICS_BY_KEY))
        raise ValueError(f"Unknown metric_key {value!r}. Valid keys: {valid_keys}.")
    return value


MetricKey = Annotated[str, AfterValidator(_validate_metric_key)]
"""A metric key validated against the registry at model-construction time.

Used by every Pydantic input model that takes a metric key (MCP tool
inputs) so an unknown key is rejected with a clear `ValidationError`
before any repository or SQL code runs — one reusable check instead of
re-validating in each command.
"""
