"""Tests for the site registry and plain-lookup site resolution.

Site ids match eBay's real SiteID values (developer.ebay.com), not an
invented scheme.
"""

import pytest

from category_insights.sites import DEFAULT_SITE_ID, SITES, get_site, match_known_site, resolve_site


def test_site_ids_are_unique() -> None:
    ids = [site.site_id for site in SITES]
    assert len(ids) == len(set(ids))


def test_get_site_raises_key_error_for_unknown_site() -> None:
    with pytest.raises(KeyError):
        get_site(999)


@pytest.mark.parametrize(
    ("mention", "expected_site_id"),
    [
        ("US", 0),
        ("us", 0),
        ("usa", 0),
        ("United States", 0),
        ("Canada", 2),
        ("ca", 2),
        ("UK", 3),
        ("United Kingdom", 3),
        ("Australia", 15),
        ("Germany", 77),
        ("de", 77),
    ],
)
def test_resolve_site_matches_name_or_alias(mention: str, expected_site_id: int) -> None:
    assert resolve_site(mention) == expected_site_id


def test_resolve_site_defaults_when_mention_is_none() -> None:
    assert resolve_site(None) == DEFAULT_SITE_ID


def test_resolve_site_defaults_for_unrecognized_mention() -> None:
    assert resolve_site("some made up place") == DEFAULT_SITE_ID


@pytest.mark.parametrize(("mention", "expected_site_id"), [("US", 0), ("canada", 2), ("uk", 3)])
def test_match_known_site_matches_name_or_alias(mention: str, expected_site_id: int) -> None:
    assert match_known_site(mention) == expected_site_id


def test_match_known_site_returns_none_for_unrecognized_mention() -> None:
    assert match_known_site("some made up place") is None


def test_match_known_site_matches_us_which_has_a_falsy_site_id() -> None:
    # Regression guard: site_id 0 (US) is falsy in Python — a naive
    # `match_known_site(...) or DEFAULT_SITE_ID` would silently discard
    # a real match for US. `resolve_site` must use an explicit None check.
    assert match_known_site("US") == 0
    assert resolve_site("US") == 0
