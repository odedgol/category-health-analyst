"""Tests for `date_ranges`: the fast deterministic path, then the LLM fallback.

`fixed_now` (conftest.py) is 2026-06-15, a Monday — chosen so week/month/
quarter boundary math has an unambiguous expected answer. `fake_chat_model`
has no configured response by default, so any test that doesn't explicitly
configure one fails loudly if the fast path unexpectedly falls through to
the LLM.
"""

from datetime import date

from category_insights.agent.date_ranges import (
    DateClassification,
    parse_known_phrase,
    resolve_date_range,
)
from tests.conftest import FakeChatModel


def test_today(fixed_now: date) -> None:
    result = parse_known_phrase("today", fixed_now)
    assert result is not None
    assert (result.start, result.end) == (fixed_now, fixed_now)


def test_yesterday(fixed_now: date) -> None:
    result = parse_known_phrase("Yesterday", fixed_now)
    assert result is not None
    assert (result.start, result.end) == (date(2026, 6, 14), date(2026, 6, 14))


def test_this_week_is_week_to_date(fixed_now: date) -> None:
    result = parse_known_phrase("this week", fixed_now)
    assert result is not None
    assert (result.start, result.end) == (date(2026, 6, 15), fixed_now)  # Monday -> today


def test_last_week_is_the_full_prior_week(fixed_now: date) -> None:
    result = parse_known_phrase("last week", fixed_now)
    assert result is not None
    assert (result.start, result.end) == (date(2026, 6, 8), date(2026, 6, 14))


def test_this_month_is_month_to_date(fixed_now: date) -> None:
    result = parse_known_phrase("MTD", fixed_now)
    assert result is not None
    assert (result.start, result.end) == (date(2026, 6, 1), fixed_now)


def test_last_month_handles_year_rollover() -> None:
    result = parse_known_phrase("last month", date(2026, 1, 15))
    assert result is not None
    assert (result.start, result.end) == (date(2025, 12, 1), date(2025, 12, 31))


def test_last_quarter_handles_year_rollover() -> None:
    result = parse_known_phrase("last quarter", date(2026, 1, 15))
    assert result is not None
    assert (result.start, result.end) == (date(2025, 10, 1), date(2025, 12, 31))


def test_last_n_days_is_inclusive_of_today(fixed_now: date) -> None:
    result = parse_known_phrase("last 7 days", fixed_now)
    assert result is not None
    assert (result.start, result.end) == (date(2026, 6, 9), fixed_now)


def test_last_n_weeks(fixed_now: date) -> None:
    result = parse_known_phrase("last 2 weeks", fixed_now)
    assert result is not None
    assert (result.start, result.end) == (date(2026, 6, 2), fixed_now)


def test_unrecognized_phrase_returns_none(fixed_now: date) -> None:
    assert parse_known_phrase("since the product launch", fixed_now) is None


def test_resolve_date_range_uses_fast_path_without_any_llm_call(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    result = resolve_date_range("last week", fake_chat_model, fixed_now)

    assert result is not None
    assert result.label == "last week"
    assert fake_chat_model.structured_call_counts == {}


def test_resolve_date_range_falls_back_to_llm_for_unrecognized_phrase(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    fake_chat_model.set_structured_response(
        DateClassification,
        DateClassification(start=date(2026, 5, 1), end=date(2026, 5, 15)),
    )

    result = resolve_date_range("the first half of May", fake_chat_model, fixed_now)

    assert result is not None
    assert (result.start, result.end) == (date(2026, 5, 1), date(2026, 5, 15))
    assert result.label == "the first half of May"
    assert fake_chat_model.structured_call_counts[DateClassification] == 1


def test_resolve_date_range_does_not_trust_a_nonsensical_llm_answer(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    fake_chat_model.set_structured_response(
        DateClassification,
        DateClassification(start=date(2026, 5, 15), end=date(2026, 5, 1)),  # start after end
    )

    result = resolve_date_range("nonsense", fake_chat_model, fixed_now)

    assert result is None


def test_resolve_date_range_llm_returning_no_answer_yields_none(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    fake_chat_model.set_structured_response(
        DateClassification, DateClassification(start=None, end=None)
    )

    result = resolve_date_range("not a real time period", fake_chat_model, fixed_now)

    assert result is None
