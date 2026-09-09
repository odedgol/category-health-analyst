"""Tests for pure answer-formatting functions — no LLM, no I/O."""

from datetime import date

from category_insights.agent.answer_formatting import (
    format_answer,
    format_metric_series,
    format_notes,
    format_period_comparison,
    format_snapshot,
)
from category_insights.domain.models import (
    CategorySnapshot,
    DateRange,
    MetricPoint,
    NoteChunk,
    PeriodComparison,
)


def test_format_period_comparison_reads_as_improvement_for_a_higher_is_better_metric() -> None:
    comparison = PeriodComparison(
        category_id=1,
        site_id=0,
        metric_key="image_count",
        period_a=DateRange(start=date(2026, 5, 1), end=date(2026, 5, 31), label="last month"),
        period_b=DateRange(start=date(2026, 6, 1), end=date(2026, 6, 15), label="this month"),
        value_a=80.0,
        value_b=90.0,
        absolute_delta=10.0,
        pct_delta=0.125,
        improved=True,
    )

    text = format_period_comparison(comparison)

    assert "Image count" in text
    assert "80 (last month)" in text
    assert "90 (this month)" in text
    assert "improvement" in text


def test_format_period_comparison_reads_as_decline_for_a_lower_is_better_metric_that_rose() -> None:
    comparison = PeriodComparison(
        category_id=1,
        site_id=0,
        metric_key="not_aligned_tax_count",
        period_a=DateRange(start=date(2026, 5, 1), end=date(2026, 5, 31), label="last month"),
        period_b=DateRange(start=date(2026, 6, 1), end=date(2026, 6, 15), label="this month"),
        value_a=5.0,
        value_b=8.0,
        absolute_delta=3.0,
        pct_delta=0.6,
        improved=False,
    )

    text = format_period_comparison(comparison)

    assert "decline" in text
    assert "improvement" not in text


def test_format_period_comparison_reads_as_no_change_for_a_zero_delta() -> None:
    comparison = PeriodComparison(
        category_id=1,
        site_id=0,
        metric_key="image_count",
        period_a=DateRange(start=date(2026, 5, 1), end=date(2026, 5, 31)),
        period_b=DateRange(start=date(2026, 6, 1), end=date(2026, 6, 15)),
        value_a=80.0,
        value_b=80.0,
        absolute_delta=0.0,
        pct_delta=0.0,
        improved=False,
    )

    assert "no change" in format_period_comparison(comparison)


def test_format_metric_series_summarizes_first_and_last() -> None:
    points = [
        MetricPoint(
            category_id=1, site_id=0, metric_key="image_count", date=date(2026, 6, 1), value=80.0
        ),
        MetricPoint(
            category_id=1, site_id=0, metric_key="image_count", date=date(2026, 6, 2), value=82.0
        ),
        MetricPoint(
            category_id=1, site_id=0, metric_key="image_count", date=date(2026, 6, 3), value=89.0
        ),
    ]

    text = format_metric_series("image_count", points)

    assert "80 -> 89" in text
    assert "3 days of data" in text


def test_format_metric_series_handles_a_single_point() -> None:
    points = [
        MetricPoint(
            category_id=1, site_id=0, metric_key="image_count", date=date(2026, 6, 1), value=80.0
        )
    ]

    assert format_metric_series("image_count", points) == "Image count on 2026-06-01: 80."


def test_format_metric_series_handles_no_data() -> None:
    assert format_metric_series("image_count", []) == "No image count data found for that range."


def test_format_snapshot_handles_missing_data() -> None:
    assert format_snapshot(None) == "No data available for that category/site as of that date."


def test_format_snapshot_lists_every_metric() -> None:
    snapshot = CategorySnapshot(
        category_id=1,
        site_id=0,
        date=date(2026, 6, 15),
        metrics={"image_count": 89.0, "missing_category_exists": 1.0},
    )

    text = format_snapshot(snapshot)

    assert "2026-06-15" in text
    assert "Image count: 89" in text
    assert "Missing category exists: yes" in text


def test_format_notes_renders_a_bulleted_list() -> None:
    notes = [
        NoteChunk(
            category_id=1,
            date=date(2026, 6, 1),
            body="Taxonomy migration explained the dip.",
            score=0.9,
        )
    ]

    text = format_notes(notes)

    assert text.startswith("Related analyst notes:")
    assert "Taxonomy migration explained the dip." in text


def test_format_notes_is_empty_string_for_no_notes() -> None:
    assert format_notes([]) == ""


def test_format_answer_joins_sections_and_drops_empty_notes() -> None:
    answer = format_answer(["line one", "line two"], note_section="")

    assert answer == "line one\n\nline two"


def test_format_answer_includes_notes_when_present() -> None:
    answer = format_answer(["line one"], note_section="Related analyst notes:\n- a note")

    assert answer == "line one\n\nRelated analyst notes:\n- a note"
