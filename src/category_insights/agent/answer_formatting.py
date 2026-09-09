"""Turns raw data-layer results into human-readable answer text.

Pure functions, no LLM calls — the numbers speak for themselves once
they're framed with the metric's display name, unit, and trend direction.
`agent.graph`'s `format_answer_node` is the only caller, composing
whichever of these apply to a given question (a comparison, a series, a
snapshot, notes) into the final answer.
"""

from category_insights.domain.models import (
    CategorySnapshot,
    DateRange,
    MetricPoint,
    NoteChunk,
    PeriodComparison,
)
from category_insights.metrics import get_metric


def _format_value(value: float, unit: str) -> str:
    if unit == "flag":
        return "yes" if value >= 1 else "no"
    return str(int(value)) if value == int(value) else f"{value:.2f}"


def _format_range(date_range: DateRange) -> str:
    return date_range.label or f"{date_range.start.isoformat()} to {date_range.end.isoformat()}"


def format_period_comparison(comparison: PeriodComparison) -> str:
    """Describe a `PeriodComparison`, framed by the metric's own trend direction.

    `comparison.improved` (not the raw sign of the delta) decides
    "improved" vs "declined" — for a lower-is-better metric, a drop is
    the improvement, and this must read that way.
    """
    metric = get_metric(comparison.metric_key)
    value_a = _format_value(comparison.value_a, metric.unit)
    value_b = _format_value(comparison.value_b, metric.unit)

    if comparison.absolute_delta == 0:
        verdict = "no change"
    else:
        verdict = "an improvement" if comparison.improved else "a decline"

    return (
        f"{metric.display_name} went from {value_a} ({_format_range(comparison.period_a)}) "
        f"to {value_b} ({_format_range(comparison.period_b)}): "
        f"{comparison.absolute_delta:+.2f} ({comparison.pct_delta:+.1%}) — {verdict}."
    )


def format_metric_series(metric_key: str, points: list[MetricPoint]) -> str:
    """Summarize a daily metric series as its first and last value.

    Deliberately not a day-by-day dump — a question asking for a range
    wants the trend, not a raw table; `get_metric_history`'s full output
    is still available to a caller that needs every point.
    """
    metric = get_metric(metric_key)
    if not points:
        return f"No {metric.display_name.lower()} data found for that range."

    first, last = points[0], points[-1]
    if len(points) == 1:
        value = _format_value(first.value, metric.unit)
        return f"{metric.display_name} on {first.date.isoformat()}: {value}."

    first_value = _format_value(first.value, metric.unit)
    last_value = _format_value(last.value, metric.unit)
    return (
        f"{metric.display_name} from {first.date.isoformat()} to {last.date.isoformat()}: "
        f"{first_value} -> {last_value} ({len(points)} days of data)."
    )


def format_snapshot(snapshot: CategorySnapshot | None) -> str:
    """Describe a point-in-time snapshot, or say plainly that there's no data."""
    if snapshot is None:
        return "No data available for that category/site as of that date."

    lines = [
        f"{get_metric(key).display_name}: {_format_value(value, get_metric(key).unit)}"
        for key, value in snapshot.metrics.items()
    ]
    return f"As of {snapshot.date.isoformat()}: " + "; ".join(lines) + "."


def format_notes(notes: list[NoteChunk]) -> str:
    """Render grounding notes as a labeled list, or `""` when there's nothing to show.

    An empty string (not a placeholder sentence) so `format_answer` can
    join sections without producing an awkward "no notes found" line when
    the question never asked for an explanation in the first place.
    """
    if not notes:
        return ""
    lines = [f"- ({note.date.isoformat()}) {note.body}" for note in notes]
    return "Related analyst notes:\n" + "\n".join(lines)


def format_answer(data_lines: list[str], note_section: str) -> str:
    """Join whichever data lines a question produced with an optional notes section."""
    sections = [line for line in data_lines if line]
    if note_section:
        sections.append(note_section)
    return "\n\n".join(sections)
