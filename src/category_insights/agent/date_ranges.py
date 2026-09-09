"""Date-phrase resolution: fast deterministic parsing, then an LLM fallback.

`parse_known_phrase` (the fast path) handles the relative phrases this
project's question set actually uses — "last week", "this month", "last N
days", and friends — with no LLM involved, the same split
`sites.match_known_site` draws between "the static/fast path" and "needs a
model." Only a phrase the fast path doesn't recognize reaches
`resolve_date_range`'s LLM fallback, which asks the model to read the
phrase against an explicit `now` and return absolute dates directly.

Structurally this mirrors `agent.site_resolution` (closed-ended fast path
first, model only for what falls through) — but unlike site aliases,
resolved phrases aren't learned/cached: a genuinely novel phrase is
unlikely to recur verbatim, so there's no reusable mapping worth
persisting.

Every calculation here takes `now: date` explicitly rather than calling
`date.today()` — see `conftest.py`'s `fixed_now` fixture — so parsing is
reproducible in tests and never drifts with the calendar.
"""

import re
from datetime import date, timedelta

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from category_insights.domain.models import DateRange
from category_insights.domain.ports import ChatModel

_LAST_N_DAYS_RE = re.compile(r"^last (\d+) days?$")
_LAST_N_WEEKS_RE = re.compile(r"^last (\d+) weeks?$")


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())  # Monday


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _quarter_start(day: date) -> date:
    quarter_first_month = ((day.month - 1) // 3) * 3 + 1
    return day.replace(month=quarter_first_month, day=1)


def _prev_month_range(now: date) -> DateRange:
    this_month_start = _month_start(now)
    last_month_end = this_month_start - timedelta(days=1)
    return DateRange(start=_month_start(last_month_end), end=last_month_end, label="last month")


def _prev_quarter_range(now: date) -> DateRange:
    this_quarter_start = _quarter_start(now)
    last_quarter_end = this_quarter_start - timedelta(days=1)
    return DateRange(
        start=_quarter_start(last_quarter_end), end=last_quarter_end, label="last quarter"
    )


def parse_known_phrase(phrase: str, now: date) -> DateRange | None:
    """The fast path: recognizes a fixed set of relative phrases against `now`.

    Recognizes: today, yesterday, this/last week, this/last month,
    this/last quarter, "last N days", "last N weeks". Case-insensitive,
    surrounding whitespace ignored. `None` if `phrase` isn't one of these
    — the caller (`resolve_date_range`) is what falls back to the LLM.
    """
    normalized = phrase.strip().lower()

    if normalized == "today":
        return DateRange(start=now, end=now, label="today")
    if normalized == "yesterday":
        yesterday = now - timedelta(days=1)
        return DateRange(start=yesterday, end=yesterday, label="yesterday")
    if normalized in ("this week", "week to date", "wtd"):
        return DateRange(start=_week_start(now), end=now, label="this week")
    if normalized == "last week":
        last_week_end = _week_start(now) - timedelta(days=1)
        return DateRange(
            start=last_week_end - timedelta(days=6), end=last_week_end, label="last week"
        )
    if normalized in ("this month", "month to date", "mtd"):
        return DateRange(start=_month_start(now), end=now, label="this month")
    if normalized == "last month":
        return _prev_month_range(now)
    if normalized in ("this quarter", "quarter to date", "qtd"):
        return DateRange(start=_quarter_start(now), end=now, label="this quarter")
    if normalized == "last quarter":
        return _prev_quarter_range(now)

    days_match = _LAST_N_DAYS_RE.match(normalized)
    if days_match:
        n = int(days_match.group(1))
        return DateRange(start=now - timedelta(days=n - 1), end=now, label=f"last {n} days")

    weeks_match = _LAST_N_WEEKS_RE.match(normalized)
    if weeks_match:
        n = int(weeks_match.group(1))
        return DateRange(start=now - timedelta(days=7 * n - 1), end=now, label=f"last {n} weeks")

    return None


class DateClassification(BaseModel):
    """The LLM's reading of a phrase the fast path didn't recognize."""

    start: date | None
    end: date | None


def _build_classification_prompt(phrase: str, now: date) -> str:
    return (
        "A user mentioned a time period that doesn't match any of the common "
        "phrases this system recognizes automatically. Work out the date "
        "range they mean and return the start and end dates (inclusive), or "
        "null for both if the phrase doesn't specify a real time period.\n\n"
        f"Today's date is {now.isoformat()}.\n\n"
        f"Phrase: {phrase!r}"
    )


def resolve_date_range(phrase: str, chat_model: ChatModel, now: date) -> DateRange | None:
    """Resolve a date phrase, falling back to an LLM for anything the fast path misses.

    1. Recognized by `parse_known_phrase` -> returned, no LLM call.
    2. Otherwise, ask the LLM for absolute start/end dates. A `None` on
       either side, or a range where `start` is after `end` — never
       trusted blindly — resolves to `None` rather than a guess.
    """
    known = parse_known_phrase(phrase, now)
    if known is not None:
        return known

    structured_model = chat_model.with_structured_output(DateClassification)
    classification = structured_model.invoke(
        [HumanMessage(content=_build_classification_prompt(phrase, now))]
    )

    if classification.start is None or classification.end is None:
        return None
    if classification.start > classification.end:
        return None
    return DateRange(start=classification.start, end=classification.end, label=phrase)
