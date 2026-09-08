"""Tests for the metric registry: the one thing every other layer trusts by key."""

import pytest

from category_insights.metrics import METRICS, TrendDirection, get_metric


def test_metric_keys_are_unique() -> None:
    keys = [metric.key for metric in METRICS]
    assert len(keys) == len(set(keys))


def test_every_metric_has_a_display_name_and_unit() -> None:
    for metric in METRICS:
        assert metric.display_name
        assert metric.unit in {"count", "flag"}
        assert metric.description


@pytest.mark.parametrize(
    ("metric_key", "expected_direction"),
    [
        ("image_count", TrendDirection.HIGHER_IS_BETTER),
        ("aligned_tax_count", TrendDirection.HIGHER_IS_BETTER),
        ("not_aligned_tax_count", TrendDirection.LOWER_IS_BETTER),
        ("missing_category_exists", TrendDirection.LOWER_IS_BETTER),
    ],
)
def test_trend_direction_matches_spec(metric_key: str, expected_direction: TrendDirection) -> None:
    assert get_metric(metric_key).trend_direction == expected_direction


def test_get_metric_raises_key_error_for_unknown_metric() -> None:
    with pytest.raises(KeyError):
        get_metric("not_a_real_metric")


def test_registry_has_exactly_four_metrics() -> None:
    assert len(METRICS) == 4
