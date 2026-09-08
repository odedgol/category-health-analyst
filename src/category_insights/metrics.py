"""Canonical metric registry.

Every module that deals with a metric by name (the DB schema, the MCP
tools, the answer formatter) imports from here rather than hardcoding a
metric key or its trend direction. Adding a metric later means adding one
entry to `METRICS` plus one column in the DB schema — nothing else in the
codebase names an individual metric.

Fields mirror what a real category-health feed actually tracks: raw
counts per category per site per day (image count, taxonomy-alignment
counts, whether a missing-category problem exists) — not invented
percentage metrics.
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
    unit: str  # "count" or "flag" (0/1)
    description: str
    trend_direction: TrendDirection


METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="image_count",
        display_name="Image count",
        unit="count",
        description="Total number of product images in this category and site.",
        trend_direction=TrendDirection.HIGHER_IS_BETTER,
    ),
    MetricDefinition(
        key="aligned_tax_count",
        display_name="Aligned taxonomy count",
        unit="count",
        description="Number of products correctly mapped to a valid leaf category.",
        trend_direction=TrendDirection.HIGHER_IS_BETTER,
    ),
    MetricDefinition(
        key="not_aligned_tax_count",
        display_name="Not-aligned taxonomy count",
        unit="count",
        description="Number of products not mapped to a valid leaf category.",
        trend_direction=TrendDirection.LOWER_IS_BETTER,
    ),
    MetricDefinition(
        key="missing_category_exists",
        display_name="Missing category exists",
        unit="flag",
        description=(
            "Whether at least one product in this category/site has no category "
            "mapping at all (1 = yes, 0 = no)."
        ),
        trend_direction=TrendDirection.LOWER_IS_BETTER,
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
