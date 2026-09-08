"""Tests for domain model validation rules."""

from datetime import date

import pytest
from pydantic import ValidationError

from category_insights.domain.models import CategoryMatch, DateRange


def test_date_range_accepts_start_before_end() -> None:
    date_range = DateRange(start=date(2026, 3, 1), end=date(2026, 3, 7))
    assert date_range.start < date_range.end


def test_date_range_accepts_start_equal_to_end() -> None:
    date_range = DateRange(start=date(2026, 3, 1), end=date(2026, 3, 1))
    assert date_range.start == date_range.end


def test_date_range_rejects_start_after_end() -> None:
    with pytest.raises(ValidationError):
        DateRange(start=date(2026, 3, 7), end=date(2026, 3, 1))


def test_category_match_rejects_invalid_confidence_literal() -> None:
    with pytest.raises(ValidationError):
        CategoryMatch(
            category_id=1, name="Women's Running Shoes", score=0.9, confidence="very-high"
        )
