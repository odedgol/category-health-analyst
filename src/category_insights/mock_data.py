"""Synthetic category-snapshot generator.

Pure data generation: given the curated category fixture
(`fixtures/categories.yaml`), the site registry, and a random seed,
produces `Category` and `MetricPoint` domain objects in memory —
deterministic for a given seed, with a slow underlying trend, daily
noise, and (for a handful of curated categories) a sharp injected event
with partial recovery, so relative date-range questions and "why did X
change" questions both have a real answer to find.

This module never touches a database; `seed_database()` is the one
function that also writes, and it does so only by calling
`DuckDbRepository` methods — never raw SQL.
"""

import random
from datetime import date, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from category_insights.db.repository import DuckDbRepository
from category_insights.domain.models import Category, MetricPoint
from category_insights.metrics import METRICS, get_metric
from category_insights.sites import DEFAULT_SITE_ID, SITES, Site

DEFAULT_FIXTURE_PATH = Path("fixtures/categories.yaml")

# (low, high) starting-baseline range per metric.
_METRIC_BASELINE_RANGE: dict[str, tuple[float, float]] = {
    "image_count": (200.0, 2000.0),
    "aligned_tax_count": (150.0, 2800.0),
    "not_aligned_tax_count": (5.0, 150.0),
    "missing_category_exists": (0.0, 0.0),  # normally no missing-category problem
}

# Standard deviation of the daily noise added on top of the trend line.
_METRIC_NOISE_SCALE: dict[str, float] = {
    "image_count": 15.0,
    "aligned_tax_count": 20.0,
    "not_aligned_tax_count": 4.0,
    "missing_category_exists": 0.0,  # flat at 0 unless an event pushes it
}

# (low, high) range for the total slow drift applied across the full
# generated window (end-of-window trend value minus start-of-window).
_METRIC_DRIFT_RANGE: dict[str, tuple[float, float]] = {
    "image_count": (-50.0, 300.0),
    "aligned_tax_count": (-80.0, 350.0),
    "not_aligned_tax_count": (-15.0, 15.0),
    "missing_category_exists": (0.0, 0.0),
}


class MetricEvent(BaseModel):
    """A sharp, deliberate step change injected into one metric, at one site, on one day."""

    metric_key: str
    site_id: int = DEFAULT_SITE_ID
    day: int
    magnitude: float
    recovery_days: int = 30
    recovery_fraction: float = 0.6


class CategoryFixture(BaseModel):
    """One curated category from `fixtures/categories.yaml`."""

    category_id: int
    name: str
    aliases: list[str] = Field(default_factory=list)
    event: MetricEvent | None = None


def load_category_fixtures(fixture_path: Path = DEFAULT_FIXTURE_PATH) -> list[CategoryFixture]:
    """Load the curated category list (aliases + any injected event) from YAML."""
    raw = yaml.safe_load(fixture_path.read_text())
    return [CategoryFixture.model_validate(entry) for entry in raw["categories"]]


def fixtures_to_categories(fixtures: list[CategoryFixture]) -> list[Category]:
    """Project fixtures down to the `Category` shape the repository stores."""
    return [
        Category(category_id=fixture.category_id, name=fixture.name, aliases=fixture.aliases)
        for fixture in fixtures
    ]


def _clip_value(metric_key: str, value: float) -> float:
    if get_metric(metric_key).unit == "flag":
        return min(1.0, max(0.0, value))
    return max(0.0, round(value))


def _event_offset(
    event: MetricEvent | None, metric_key: str, site_id: int, day_index: int
) -> float:
    """The event's contribution to `metric_key`/`site_id` on `day_index`, or 0 if it doesn't apply.

    The full `magnitude` applies starting on `event.day`; it then linearly
    recovers `recovery_fraction` of itself over `recovery_days`, leaving a
    permanent partial effect afterward — a temporary dip that never fully
    heals, matching how a real backfill-in-progress would look.
    """
    if (
        event is None
        or event.metric_key != metric_key
        or event.site_id != site_id
        or day_index < event.day
    ):
        return 0.0

    days_since_event = day_index - event.day
    recovery_progress = min(days_since_event / event.recovery_days, 1.0)
    return event.magnitude * (1 - event.recovery_fraction * recovery_progress)


def _generate_series(
    rng: random.Random, metric_key: str, site_id: int, days: int, event: MetricEvent | None
) -> list[float]:
    """Generate `days` daily values for one metric at one site: trend + noise + event."""
    baseline_low, baseline_high = _METRIC_BASELINE_RANGE[metric_key]
    baseline = rng.uniform(baseline_low, baseline_high)  # noqa: S311 (mock data, not security-sensitive)

    drift_low, drift_high = _METRIC_DRIFT_RANGE[metric_key]
    total_drift = rng.uniform(drift_low, drift_high)  # noqa: S311
    noise_scale = _METRIC_NOISE_SCALE[metric_key]

    values: list[float] = []
    for day_index in range(days):
        trend_value = baseline + total_drift * (day_index / max(days - 1, 1))
        noisy_value = trend_value + (rng.gauss(0.0, noise_scale) if noise_scale else 0.0)
        noisy_value += _event_offset(event, metric_key, site_id, day_index)
        values.append(_clip_value(metric_key, noisy_value))
    return values


def generate_metric_points(
    fixtures: list[CategoryFixture],
    days: int,
    end_date: date,
    seed: int,
    sites: tuple[Site, ...] = SITES,
) -> list[MetricPoint]:
    """Generate `days` daily snapshots per category per site per metric, ending on `end_date`.

    Deterministic for a given `(fixtures, days, end_date, seed, sites)` —
    the same inputs always produce the same series, which is what makes
    the UI's "reset mock data" a reproducible reset rather than a shuffle
    that would desync generated events from the curated notes fixture.
    """
    rng = random.Random(seed)  # noqa: S311 (mock data, not security-sensitive)
    start_date = end_date - timedelta(days=days - 1)

    points: list[MetricPoint] = []
    for fixture in sorted(fixtures, key=lambda f: f.category_id):
        for site in sites:
            for metric in METRICS:
                series = _generate_series(rng, metric.key, site.site_id, days, fixture.event)
                for day_index, value in enumerate(series):
                    points.append(
                        MetricPoint(
                            category_id=fixture.category_id,
                            site_id=site.site_id,
                            metric_key=metric.key,
                            date=start_date + timedelta(days=day_index),
                            value=value,
                        )
                    )
    return points


def seed_database(
    repository: DuckDbRepository,
    *,
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    days: int = 120,
    end_date: date | None = None,
    seed: int = 42,
) -> None:
    """Generate mock data and persist it via the repository layer.

    The only I/O here is reading the fixture YAML and calling
    `repository.insert_categories` / `insert_metric_points` — no SQL is
    ever written in this module.
    """
    fixtures = load_category_fixtures(fixture_path)
    categories = fixtures_to_categories(fixtures)
    points = generate_metric_points(fixtures, days, end_date or date.today(), seed)

    repository.insert_categories(categories)
    repository.insert_metric_points(points)
