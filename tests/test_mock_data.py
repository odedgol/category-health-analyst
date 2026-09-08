"""Tests for the pure mock-data generation functions (no database involved)."""

from datetime import date

import pytest

from category_insights.domain.models import Category, MetricPoint
from category_insights.mock_data import (
    DEFAULT_FIXTURE_PATH,
    CategoryFixture,
    MetricEvent,
    fixtures_to_categories,
    generate_metric_points,
    load_category_fixtures,
)
from category_insights.sites import SITES


def test_real_fixture_has_at_least_three_events_and_three_aliased_categories() -> None:
    fixtures = load_category_fixtures(DEFAULT_FIXTURE_PATH)
    assert len(fixtures) >= 15
    assert sum(1 for f in fixtures if f.event is not None) >= 3
    assert sum(1 for f in fixtures if f.aliases) >= 3


def test_fixtures_to_categories_preserves_aliases() -> None:
    fixtures = [CategoryFixture(category_id=1, name="Widgets", aliases=["gadgets"])]
    categories = fixtures_to_categories(fixtures)
    assert categories == [Category(category_id=1, name="Widgets", aliases=["gadgets"])]


def test_generate_metric_points_is_deterministic_for_the_same_seed() -> None:
    fixtures = [CategoryFixture(category_id=1, name="Widgets", aliases=[])]
    first_run = generate_metric_points(fixtures, days=30, end_date=date(2026, 6, 15), seed=7)
    second_run = generate_metric_points(fixtures, days=30, end_date=date(2026, 6, 15), seed=7)
    assert first_run == second_run


def test_generate_metric_points_differs_for_a_different_seed() -> None:
    fixtures = [CategoryFixture(category_id=1, name="Widgets", aliases=[])]
    run_a = generate_metric_points(fixtures, days=30, end_date=date(2026, 6, 15), seed=7)
    run_b = generate_metric_points(fixtures, days=30, end_date=date(2026, 6, 15), seed=8)
    assert run_a != run_b


def test_generates_a_row_per_category_per_site_per_metric_per_day() -> None:
    fixtures = [CategoryFixture(category_id=1, name="Widgets", aliases=[])]
    points = generate_metric_points(fixtures, days=10, end_date=date(2026, 6, 15), seed=42)
    assert len(points) == 10 * len(SITES) * 4  # 4 metrics in the registry
    assert {p.site_id for p in points} == {site.site_id for site in SITES}


def test_counts_stay_non_negative() -> None:
    fixtures = [CategoryFixture(category_id=1, name="Widgets", aliases=[])]
    points = generate_metric_points(fixtures, days=120, end_date=date(2026, 6, 15), seed=42)
    assert all(point.value >= 0.0 for point in points)


def test_missing_category_exists_stays_within_zero_and_one() -> None:
    fixtures = [CategoryFixture(category_id=1, name="Widgets", aliases=[])]
    points = generate_metric_points(fixtures, days=120, end_date=date(2026, 6, 15), seed=42)
    flag_values = [p.value for p in points if p.metric_key == "missing_category_exists"]
    assert flag_values  # sanity: the metric is actually present
    assert all(0.0 <= value <= 1.0 for value in flag_values)


def test_injected_event_produces_a_sharp_drop_with_partial_recovery() -> None:
    """Compares a run with an event against an identical run without one.

    The event never consumes randomness (it's added after the trend+noise
    value is computed), so with the same seed the two runs are identical
    except for the event's own contribution — isolating its effect from
    the metric's independently-random drift, which a same-run
    before/after comparison can't do (a strong positive drift can hide a
    real event, which is what made an earlier version of this test flaky).
    """
    base_fixture = CategoryFixture(category_id=1, name="Widgets", aliases=[])
    event_fixture = base_fixture.model_copy(
        update={
            "event": MetricEvent(
                metric_key="aligned_tax_count",
                site_id=0,
                day=10,
                magnitude=-150.0,
                recovery_days=10,
                recovery_fraction=0.6,
            )
        }
    )

    with_event = generate_metric_points(
        [event_fixture], days=30, end_date=date(2026, 6, 15), seed=1
    )
    without_event = generate_metric_points(
        [base_fixture], days=30, end_date=date(2026, 6, 15), seed=1
    )

    def series(points: list[MetricPoint]) -> dict[date, float]:
        return {
            p.date: p.value
            for p in points
            if p.metric_key == "aligned_tax_count" and p.site_id == 0
        }

    with_event_series = series(with_event)
    without_event_series = series(without_event)
    dates_sorted = sorted(with_event_series.keys())

    at_event_diff = with_event_series[dates_sorted[10]] - without_event_series[dates_sorted[10]]
    well_after_diff = with_event_series[dates_sorted[25]] - without_event_series[dates_sorted[25]]

    assert at_event_diff == pytest.approx(-150.0, abs=1.0)  # full magnitude applies immediately
    assert well_after_diff == pytest.approx(-150.0 * (1 - 0.6), abs=1.0)  # permanent partial effect
    assert well_after_diff > at_event_diff  # it partially recovered


def test_injected_event_only_applies_at_its_configured_site() -> None:
    fixtures = [
        CategoryFixture(
            category_id=1,
            name="Widgets",
            aliases=[],
            event=MetricEvent(metric_key="image_count", site_id=2, day=10, magnitude=-500.0),
        )
    ]
    points = generate_metric_points(fixtures, days=20, end_date=date(2026, 6, 15), seed=1)

    us_series = sorted(
        (p for p in points if p.metric_key == "image_count" and p.site_id == 0),
        key=lambda p: p.date,
    )
    ca_series = sorted(
        (p for p in points if p.metric_key == "image_count" and p.site_id == 2),
        key=lambda p: p.date,
    )

    us_before = sum(p.value for p in us_series[5:10]) / 5
    us_at_event = sum(p.value for p in us_series[10:12]) / 2
    ca_before = sum(p.value for p in ca_series[5:10]) / 5
    ca_at_event = sum(p.value for p in ca_series[10:12]) / 2

    assert abs(us_at_event - us_before) < 50  # US (site 0) is unaffected
    assert ca_at_event - ca_before < -300  # Canada (site 2), where the event was configured, drops
