"""CLI: (re)generate mock category data into the DuckDB warehouse.

Usage:
    uv run python -m scripts.seed_mock_data --days 120 --reset
"""

import argparse
from datetime import date
from pathlib import Path

from category_insights.db.connection import connect, reset_schema
from category_insights.db.repository import DuckDbRepository
from category_insights.mock_data import DEFAULT_FIXTURE_PATH, seed_database
from category_insights.settings import Settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the DuckDB warehouse with mock category data."
    )
    parser.add_argument(
        "--days", type=int, default=120, help="Number of daily snapshots to generate."
    )
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the schema first.")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed (defaults to Settings' configured seed).",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Path to the curated category fixture YAML.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = Settings()

    connection = connect(settings.category_insights_db_path)
    if args.reset:
        reset_schema(connection)

    repository = DuckDbRepository(connection)
    seed = args.seed if args.seed is not None else settings.category_insights_mock_data_seed
    seed_database(
        repository,
        fixture_path=args.fixture,
        days=args.days,
        end_date=date.today(),
        seed=seed,
    )
    print(  # noqa: T201 (CLI output, not library code)
        f"Seeded {args.days} days of mock data (seed={seed}) into "
        f"{settings.category_insights_db_path}"
    )


if __name__ == "__main__":
    main()
