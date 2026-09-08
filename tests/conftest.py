"""Shared pytest fixtures.

Fixtures are added here as the sprint that needs them lands, rather than
stubbed out ahead of time — a fixture with no current user is dead weight
until something actually depends on it.
"""

from datetime import date

import pytest


@pytest.fixture
def fixed_now() -> date:
    """A fixed reference date for deterministic date-range parsing tests.

    Never call `date.today()` inside parsing logic — always resolve
    relative phrases ("last week") against an explicit `now` so tests
    don't depend on when they happen to run.
    """
    return date(2026, 6, 15)
