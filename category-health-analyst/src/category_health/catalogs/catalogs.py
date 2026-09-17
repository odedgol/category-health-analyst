"""Load and resolve the project's static site and metric catalogs."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def normalize_phrase(value: str) -> str:
    """Normalize harmless formatting differences without fuzzy matching."""

    # Models commonly use snake_case for tool arguments. Treat underscores like
    # spaces so query qualifiers can still be removed deterministically.
    normalized = re.sub(
        r"[^\w]+", " ", value.casefold().replace("_", " "), flags=re.UNICODE
    )
    return " ".join(normalized.split())


@dataclass(frozen=True)
class SiteDefinition:
    site_id: int
    name: str
    country: str
    abbreviation: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    display_name: str
    unit: str
    aliases: tuple[str, ...]


class SiteCatalog:
    """Resolve site mentions against a closed, statically loaded catalog."""

    def __init__(self, sites: tuple[SiteDefinition, ...]) -> None:
        self.sites = sites
        self._by_alias: dict[str, SiteDefinition] = {}

        country_counts: dict[str, int] = {}
        for site in sites:
            normalized_country = normalize_phrase(site.country)
            country_counts[normalized_country] = country_counts.get(normalized_country, 0) + 1

        for site in sites:
            aliases = [site.name, site.abbreviation, *site.aliases]
            normalized_country = normalize_phrase(site.country)
            if country_counts[normalized_country] == 1:
                aliases.append(site.country)

            for alias in aliases:
                normalized = normalize_phrase(alias)
                existing = self._by_alias.get(normalized)
                if existing is not None and existing.site_id != site.site_id:
                    raise ValueError(f"Duplicate site alias: {alias}")
                self._by_alias[normalized] = site

    def resolve(self, mention: str) -> SiteDefinition | None:
        normalized = normalize_phrase(mention)
        if normalized.isdigit():
            site_id = int(normalized)
            return next((site for site in self.sites if site.site_id == site_id), None)
        return self._by_alias.get(normalized)


class MetricCatalog:
    """Resolve metric phrases against a closed, statically loaded catalog."""

    _QUERY_QUALIFIERS = frozenset(
        {
            "change",
            "changes",
            "comparison",
            "comparisons",
            "compare",
            "daily",
            "historical",
            "latest",
            "metric",
            "metrics",
            "monthly",
            "snapshot",
            "snapshots",
            "trend",
            "trends",
            "value",
            "values",
            "weekly",
        }
    )

    def __init__(self, metrics: tuple[MetricDefinition, ...]) -> None:
        self.metrics = metrics
        self._by_alias: dict[str, MetricDefinition] = {}
        for metric in metrics:
            for alias in (metric.metric_id, metric.display_name, *metric.aliases):
                normalized = normalize_phrase(alias)
                existing = self._by_alias.get(normalized)
                if existing is not None and existing.metric_id != metric.metric_id:
                    raise ValueError(f"Duplicate metric alias: {alias}")
                self._by_alias[normalized] = metric

    def resolve(self, mention: str) -> MetricDefinition | None:
        normalized = normalize_phrase(mention)
        exact_match = self._by_alias.get(normalized)
        if exact_match is not None:
            return exact_match

        # The model may preserve harmless query-language words in the metric
        # argument (for example, "daily image count"). Remove only a closed
        # allow-list of qualifiers, then require an exact catalog match. This
        # stays deterministic and cannot turn an unknown metric into a fuzzy hit.
        metric_only = " ".join(
            token for token in normalized.split() if token not in self._QUERY_QUALIFIERS
        )
        return self._by_alias.get(metric_only)


def _load_yaml(path: Path, root_key: str) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        document = yaml.safe_load(file)
    records = document.get(root_key)
    if not isinstance(records, list):
        raise ValueError(f"{path} must contain a list under {root_key!r}")
    return records


def load_site_catalog(path: Path) -> SiteCatalog:
    sites = tuple(
        SiteDefinition(
            site_id=int(record["site_id"]),
            name=str(record["name"]),
            country=str(record["country"]),
            abbreviation=str(record["abbreviation"]),
            aliases=tuple(str(alias) for alias in record.get("aliases", [])),
        )
        for record in _load_yaml(path, "sites")
    )
    return SiteCatalog(sites)


def load_metric_catalog(path: Path) -> MetricCatalog:
    metrics = tuple(
        MetricDefinition(
            metric_id=str(record["id"]),
            display_name=str(record["display_name"]),
            unit=str(record["unit"]),
            aliases=tuple(str(alias) for alias in record.get("aliases", [])),
        )
        for record in _load_yaml(path, "metrics")
    )
    return MetricCatalog(metrics)
