"""Pure calculations over stored domain values."""

from decimal import Decimal

from category_health.domain.models import CategorySiteMetrics, MetricComparison


def compare_percentages(previous: Decimal, current: Decimal) -> MetricComparison:
    """Compare two stored percentage values.

    The delta is expressed in percentage points. For example, 72% to 69%
    produces -3 percentage points, not -3%.
    """

    return MetricComparison(
        previous_value=previous,
        current_value=current,
        absolute_delta=current - previous,
        percentage_point_delta=current - previous,
    )


def latest_update(updates: list[CategorySiteMetrics]) -> CategorySiteMetrics:
    """Return the update with the greatest LMD.

    LMD is the update ordering key for version 1. An empty collection is a
    domain error because there is no meaningful latest update.
    """

    if not updates:
        raise ValueError("Cannot select a latest update from an empty collection")
    return max(updates, key=lambda update: update.last_modified_at)
