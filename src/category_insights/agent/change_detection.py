"""Change-point detection: flags the day(s) a metric moved unusually much.

Used only when a "why did X change" question doesn't say which period —
see `agent.graph`'s `detect_change_node`. Turns "I don't know which
period you mean" into a concrete, data-grounded clarifying question
("I see a notable change around 2026-07-15 — is that the one?") instead
of silently falling back to a plain snapshot that never actually answers
what changed, or to a generic "which category" -style dead end.

Ranks day-over-day deltas by a *robust* z-score (median + median absolute
deviation, not mean + standard deviation) — no LLM, no guessing at what
counts as "significant." Robust statistics matter specifically because
this can be asked to find more than one change point: an ordinary
mean/stdev z-score is itself dragged around by the very outliers it's
trying to detect, so a second, smaller-but-still-real step can end up
*less* significant once a bigger one is added to the series, purely
because the bigger one inflated the mean and stdev. Median and MAD
aren't pulled off-center by a handful of extreme points, so multiple
distinct events each score close to how significant they actually are.

The threshold is high on purpose: it only fires for the kind of sharp,
deliberate step `mock_data.py`'s events inject (see its `_event_offset`
— a step that then recovers gradually, so only the step itself, not the
recovery, is ever this sharp), never for ordinary day-to-day drift.
"""

import statistics
from datetime import date

from category_insights.domain.models import MetricPoint

MIN_Z_SCORE = 6.0
"""How many (robust) standard deviations past the median delta counts as a real
change, not noise.

Calibrated against the real seeded mock warehouse (`scripts.seed_mock_data`,
120 days, the default `CATEGORY_INSIGHTS_MOCK_DATA_SEED`), not chosen
abstractly: across every category/metric series, the 4 real injected
events scored 7.97-27.65, and the single highest score among the ~70
series with *no* injected event (pure noise) was 5.06 — a textbook
3.0 "looks statistically significant" threshold is nowhere near
strict enough here, because with dozens of series each contributing many
day-over-day deltas, *something* clears 3 sigma by pure chance most of
the time (a multiple-comparisons problem, not a bug in the statistic
itself). 6.0 sits in the gap with real margin on both sides."""

MAX_CANDIDATES = 2
"""At most this many dates are ever offered in one clarifying question — more would
be a data dump, not a question someone can actually answer."""

_MAD_TO_STDEV = 1.4826
"""Scales MAD to be comparable to a standard deviation, for a normally-distributed
series — the standard constant for a robust z-score."""


def find_change_points(
    points: list[MetricPoint],
    max_candidates: int = MAX_CANDIDATES,
    min_z_score: float = MIN_Z_SCORE,
) -> list[date]:
    """Return up to `max_candidates` dates where the metric moved unusually much.

    Ranked by a robust z-score (median absolute deviation, not mean/
    stdev — see the module docstring for why) of the day-over-day delta
    magnitude, most significant first. `[]` when there's too little data
    (fewer than 3 points) or nothing clears the bar — an honest "nothing
    stands out," never a guess.
    """
    if len(points) < 3:
        return []

    deltas = [
        (points[i].date, points[i].value - points[i - 1].value) for i in range(1, len(points))
    ]
    magnitudes = [abs(delta) for _, delta in deltas]

    median = statistics.median(magnitudes)
    mad = statistics.median(abs(magnitude - median) for magnitude in magnitudes)
    # A discrete/low-noise series can have a zero MAD (most deltas share the
    # exact median) even though the data isn't perfectly flat — pstdev as a
    # fallback denominator still catches that spread; only a truly flat
    # series (pstdev also 0) yields no candidates.
    denominator = (_MAD_TO_STDEV * mad) if mad else statistics.pstdev(magnitudes)
    if denominator == 0:
        return []

    scored = [
        (day, (magnitude - median) / denominator)
        for (day, _), magnitude in zip(deltas, magnitudes, strict=True)
    ]
    significant = sorted(
        (item for item in scored if item[1] >= min_z_score), key=lambda item: item[1], reverse=True
    )
    return [day for day, _ in significant[:max_candidates]]
