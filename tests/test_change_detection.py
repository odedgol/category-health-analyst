"""Tests for `find_change_points`: pure statistics, no LLM, no I/O.

Baseline noise below uses varied, non-repeating decimal deltas
deliberately — real day-over-day noise (a Gaussian) essentially never
ties, but small hand-written integer test data easily does, which
degenerates the median-absolute-deviation denominator to exactly 0 and
falls back to `pstdev` (see `find_change_points`'s docstring). That
fallback exists so a genuinely degenerate series never divides by zero,
not to be the common case a test should exercise — varied noise here
keeps these tests representative of the real, continuous series
`find_change_points` actually runs against.
"""

from datetime import date, timedelta

from category_insights.agent.change_detection import find_change_points
from category_insights.domain.models import MetricPoint

_BASELINE_NOISE = [1.3, -2.1, 0.7, 2.4, -1.6, 1.9, -0.8, 1.2, -2.3, 0.6, 1.7, -1.1, 0.9, -1.8, 1.4]
"""15 varied, non-tied deltas — the noise floor every test below is measured against."""


def _series(start_value: float, deltas: list[float]) -> list[float]:
    values = [start_value]
    for delta in deltas:
        values.append(values[-1] + delta)
    return values


def _points(values: list[float], start: date = date(2026, 1, 1)) -> list[MetricPoint]:
    return [
        MetricPoint(
            category_id=1,
            site_id=0,
            metric_key="image_count",
            date=start + timedelta(days=i),
            value=value,
        )
        for i, value in enumerate(values)
    ]


def test_no_candidates_for_too_few_points() -> None:
    assert find_change_points(_points([100.0, 101.0])) == []


def test_no_candidates_for_a_flat_series() -> None:
    assert find_change_points(_points([100.0] * 10)) == []


def test_no_candidates_when_deltas_are_all_equal() -> None:
    # Every day moves by exactly the same amount — no spread to be an outlier against.
    assert find_change_points(_points([100.0 + i for i in range(10)])) == []


def test_no_candidates_for_pure_noise_with_no_real_spike() -> None:
    values = _series(100.0, _BASELINE_NOISE)
    assert find_change_points(_points(values)) == []


def test_detects_a_sharp_step_against_a_quiet_baseline() -> None:
    # A single large, deliberate step (mirroring mock_data.py's injected
    # events) after a noisy-but-ordinary baseline.
    values = _series(100.0, _BASELINE_NOISE + [-500.0, 1.1, -0.9, 0.3])
    step_day = date(2026, 1, 1) + timedelta(days=len(_BASELINE_NOISE) + 1)

    assert find_change_points(_points(values)) == [step_day]


def test_ranks_the_larger_of_two_distinct_steps_first() -> None:
    deltas = _BASELINE_NOISE + [-500.0, 1.1, -0.9, 0.3] + [-1500.0, 0.8, -1.2, 0.4]
    values = _series(100.0, deltas)
    start = date(2026, 1, 1)
    step_a_day = start + timedelta(days=len(_BASELINE_NOISE) + 1)
    step_b_day = start + timedelta(days=len(_BASELINE_NOISE) + 4 + 1)

    candidates = find_change_points(_points(values), max_candidates=2)

    assert candidates == [step_b_day, step_a_day]


def test_max_candidates_caps_the_result() -> None:
    deltas = _BASELINE_NOISE + [-500.0, 1.1, -0.9, 0.3] + [-1500.0, 0.8, -1.2, 0.4]
    values = _series(100.0, deltas)

    candidates = find_change_points(_points(values), max_candidates=1)

    assert len(candidates) == 1


def test_min_z_score_controls_the_sensitivity() -> None:
    values = _series(100.0, _BASELINE_NOISE + [-500.0, 1.1, -0.9, 0.3])

    assert find_change_points(_points(values), min_z_score=10_000.0) == []
