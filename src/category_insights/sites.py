"""Canonical site registry.

Mirrors `metrics.py`'s pattern: a small fixed list, not a database table.
Category data is tracked per (category, site, day) — the same category
can have different numbers in different regions, exactly like a real
multi-region catalog.

Site ids match eBay's real SiteID values (developer.ebay.com's
SiteID-to-GlobalID mapping) rather than an invented scheme — using a
real, checkable numbering is more honest mock data than 0/1/2/3.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    """One region/site the catalog operates in."""

    site_id: int
    name: str


SITES: tuple[Site, ...] = (
    Site(site_id=0, name="US"),
    Site(site_id=2, name="Canada"),
    Site(site_id=3, name="UK"),
    Site(site_id=15, name="Australia"),
    Site(site_id=77, name="Germany"),
)

SITES_BY_ID: dict[int, Site] = {site.site_id: site for site in SITES}

DEFAULT_SITE_ID = 0
"""Used when a question doesn't mention a site — the US site."""

_ALIASES_BY_SITE_ID: dict[int, tuple[str, ...]] = {
    0: ("us", "usa", "united states", "america"),
    2: ("canada", "ca"),
    3: ("uk", "united kingdom", "britain", "gb"),
    15: ("australia", "au"),
    77: ("germany", "de", "deutschland"),
}

_SITE_ID_BY_ALIAS: dict[str, int] = {
    alias: site_id for site_id, aliases in _ALIASES_BY_SITE_ID.items() for alias in aliases
}


def get_site(site_id: int) -> Site:
    """Look up a site by id.

    Raises:
        KeyError: if `site_id` isn't in the registry.
    """
    return SITES_BY_ID[site_id]


def resolve_site(mention: str | None) -> int:
    """Resolve a site mention (e.g. "Canada", "us") to a site_id.

    Plain exact/alias matching, not a Chain of Responsibility — sites are
    a small, closed set (five regions), so there's no fuzzy-matching case
    worth the added machinery that `agent.category_resolution` needs for
    an open-ended, aliased category list. Defaults to `DEFAULT_SITE_ID`
    when `mention` is `None` or unrecognized, rather than asking for
    clarification — an unrecognized site is far less consequential than
    an unrecognized category.
    """
    if mention is None:
        return DEFAULT_SITE_ID
    normalized = mention.strip().lower()
    for site in SITES:
        if site.name.lower() == normalized:
            return site.site_id
    return _SITE_ID_BY_ALIAS.get(normalized, DEFAULT_SITE_ID)
