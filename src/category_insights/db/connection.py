"""DuckDB connection management and schema bootstrap.

The schema (table + column names) is built once, from the fixed, internal
`metrics.METRICS` registry — never from caller-supplied data — so
assembling the `CREATE TABLE` statement with string joins is safe DDL
construction, not the SQL-injection risk that parameterization guards
against. `repository.py` is where caller-supplied values (category ids,
dates, metric keys) meet SQL, and that's where parameterization matters.
"""

from pathlib import Path

import duckdb

from category_insights.metrics import METRICS

_CATEGORIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    aliases VARCHAR[] NOT NULL DEFAULT []
)
"""

_LEARNED_SITE_ALIASES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS learned_site_aliases (
    alias VARCHAR PRIMARY KEY,
    site_id INTEGER NOT NULL
)
"""


def _metrics_table_sql() -> str:
    """Build the `category_daily_metrics` DDL from the metric registry.

    One column per registered metric, all DOUBLE — column names come
    straight from `metrics.METRICS`, a fixed internal registry, not from
    any request the system ever receives. Keyed by (category_id, site_id,
    date): the same category has different numbers per site/region.
    """
    metric_columns = ",\n    ".join(f"{metric.key} DOUBLE" for metric in METRICS)
    return (
        "CREATE TABLE IF NOT EXISTS category_daily_metrics (\n"
        "    category_id INTEGER NOT NULL REFERENCES categories(category_id),\n"
        "    site_id INTEGER NOT NULL,\n"
        "    date DATE NOT NULL,\n"
        f"    {metric_columns},\n"
        "    PRIMARY KEY (category_id, site_id, date)\n"
        ")"
    )


def bootstrap_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create the `categories`, `category_daily_metrics`, and `learned_site_aliases` tables."""
    connection.execute(_CATEGORIES_TABLE_SQL)
    connection.execute(_metrics_table_sql())
    connection.execute(_LEARNED_SITE_ALIASES_TABLE_SQL)


def reset_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Drop and recreate all tables — used by `seed_mock_data.py --reset`.

    Deliberately does *not* drop `learned_site_aliases` — a mock-data
    reset regenerates metrics and categories, but learned site aliases
    aren't mock data; they're real value accumulated from real questions,
    and resetting them would defeat the point of learning them at all.
    """
    connection.execute("DROP TABLE IF EXISTS category_daily_metrics")
    connection.execute("DROP TABLE IF EXISTS categories")
    bootstrap_schema(connection)


def connect(db_path: Path, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open (creating if absent) the DuckDB warehouse file at `db_path`.

    Bootstraps the schema on every non-read-only connection, so callers
    never need to remember to do it themselves — `CREATE TABLE IF NOT
    EXISTS` makes this a no-op once the schema already exists.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(db_path), read_only=read_only)
    if not read_only:
        bootstrap_schema(connection)
    return connection
