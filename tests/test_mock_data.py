"""Tests for the pure mock-data generation functions (no database involved)."""

from datetime import date

from category_insights.domain.models import Category
from category_insights.mock_data import (
    DEFAULT_FIXTURE_PATH,
    CategoryFixture,
    MetricEvent,
    fixtures_to_categories,
    generate_metric_points,
    load_category_fixtures,
)


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


def test_percentage_metrics_stay_within_zero_and_one_hundred() -> None:
    fixtures = [CategoryFixture(category_id=1, name="Widgets", aliases=[])]
    points = generate_metric_points(fixtures, days=120, end_date=date(2026, 6, 15), seed=42)
    for point in points:
        if point.metric_key != "product_count":
            assert 0.0 <= point.value <= 100.0


def test_product_count_stays_positive() -> None:
    fixtures = [CategoryFixture(category_id=1, name="Widgets", aliases=[])]
    points = generate_metric_points(fixtures, days=120, end_date=date(2026, 6, 15), seed=42)
    product_counts = [p.value for p in points if p.metric_key == "product_count"]
    assert all(value >= 1.0 for value in product_counts)


def test_injected_event_produces_a_sharp_drop_with_partial_recovery() -> None:
    fixtures = [
        CategoryFixture(
            category_id=1,
            name="Widgets",
            aliases=[],
            event=MetricEvent(
                metric_key="taxonomy_alignment_pct",
                day=10,
                magnitude=-15.0,
                recovery_days=10,
                recovery_fraction=0.6,
            ),
        )
    ]
    points = generate_metric_points(fixtures, days=30, end_date=date(2026, 6, 15), seed=1)
    series = {
        point.date: point.value for point in points if point.metric_key == "taxonomy_alignment_pct"
    }
    dates_sorted = sorted(series.keys())

    before_event = sum(series[d] for d in dates_sorted[5:10]) / 5  # days 5-9
    at_event = sum(series[d] for d in dates_sorted[10:12]) / 2  # days 10-11, just after the drop
    well_after_recovery_window = (
        sum(series[d] for d in dates_sorted[24:29]) / 5
    )  # days 24-28, past day 10+recovery_days=20

    assert at_event - before_event < -8  # a real drop happened
    assert well_after_recovery_window > at_event + 3  # it partially recovered
    assert well_after_recovery_window < before_event  # but never fully healed
