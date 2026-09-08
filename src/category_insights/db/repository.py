"""DuckDB adapter implementing `MetricsRepository`.

Every caller-supplied *value* (a category id, a date) reaches SQL only
through a `?` placeholder — DuckDB parameterizes those, so they can never
be interpreted as SQL syntax. The one exception is `metric_key`, which
becomes a *column name* rather than a value; SQL has no placeholder syntax
for identifiers, so the safe pattern is different: `metric_key` is checked
against `metrics.METRICS_BY_KEY` — a fixed allowlist — before it ever
touches a query string, and an unknown key raises before any SQL runs.
"""

from datetime import date

import duckdb

from category_insights.domain.models import (
    Category,
    CategorySnapshot,
    DateRange,
    MetricPoint,
    PeriodComparison,
)
from category_insights.domain.ports import MetricDataUnavailableError
from category_insights.metrics import METRICS, TrendDirection, get_metric


class DuckDbRepository:
    """`MetricsRepository` implementation backed by a local DuckDB file.

    Also exposes bulk-insert methods (`insert_categories`,
    `insert_metric_points`) that aren't part of `MetricsRepository` — the
    agent and MCP tools never need to write data, only the mock-data seed
    script does, so write access is deliberately not part of the port the
    rest of the system depends on.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection

    def list_categories(self) -> list[Category]:
        rows = self._connection.execute(
            "SELECT category_id, name, aliases FROM categories ORDER BY category_id"
        ).fetchall()
        return [
            Category(category_id=category_id, name=name, aliases=list(aliases))
            for category_id, name, aliases in rows
        ]

    def get_metric_series(
        self, category_id: int, metric_key: str, start: date, end: date
    ) -> list[MetricPoint]:
        get_metric(metric_key)  # raises KeyError for an unknown metric before touching SQL
        query = (
            f"SELECT date, {metric_key} FROM category_daily_metrics "  # noqa: S608
            "WHERE category_id = ? AND date BETWEEN ? AND ? "
            "ORDER BY date"
        )
        rows = self._connection.execute(query, [category_id, start, end]).fetchall()
        return [
            MetricPoint(category_id=category_id, metric_key=metric_key, date=row_date, value=value)
            for row_date, value in rows
            if value is not None
        ]

    def compare_periods(
        self, category_id: int, metric_key: str, period_a: DateRange, period_b: DateRange
    ) -> PeriodComparison:
        value_a = self._average_metric_value(category_id, metric_key, period_a)
        value_b = self._average_metric_value(category_id, metric_key, period_b)

        absolute_delta = value_b - value_a
        pct_delta = 0.0 if value_a == 0 else absolute_delta / value_a

        trend_direction = get_metric(metric_key).trend_direction
        improved = (
            value_b > value_a
            if trend_direction == TrendDirection.HIGHER_IS_BETTER
            else value_b < value_a
        )

        return PeriodComparison(
            category_id=category_id,
            metric_key=metric_key,
            period_a=period_a,
            period_b=period_b,
            value_a=value_a,
            value_b=value_b,
            absolute_delta=absolute_delta,
            pct_delta=pct_delta,
            improved=improved,
        )

    def _average_metric_value(self, category_id: int, metric_key: str, period: DateRange) -> float:
        get_metric(metric_key)  # raises KeyError for an unknown metric before touching SQL
        query = (
            f"SELECT AVG({metric_key}) FROM category_daily_metrics "  # noqa: S608
            "WHERE category_id = ? AND date BETWEEN ? AND ?"
        )
        (average,) = self._connection.execute(
            query, [category_id, period.start, period.end]
        ).fetchone()
        if average is None:
            raise MetricDataUnavailableError(
                f"No {metric_key} data for category {category_id} "
                f"between {period.start} and {period.end}."
            )
        return float(average)

    def get_latest_snapshot(
        self, category_id: int, as_of_date: date | None = None
    ) -> CategorySnapshot | None:
        metric_columns = ", ".join(metric.key for metric in METRICS)
        query = (
            f"SELECT date, {metric_columns} FROM category_daily_metrics "  # noqa: S608
            "WHERE category_id = ? AND date <= ? "
            "ORDER BY date DESC LIMIT 1"
        )
        as_of = as_of_date if as_of_date is not None else date.max
        row = self._connection.execute(query, [category_id, as_of]).fetchone()
        if row is None:
            return None

        snapshot_date, *values = row
        metrics = {
            metric.key: value
            for metric, value in zip(METRICS, values, strict=True)
            if value is not None
        }
        return CategorySnapshot(category_id=category_id, date=snapshot_date, metrics=metrics)

    def insert_categories(self, categories: list[Category]) -> None:
        """Bulk-insert categories. Used only by the mock-data seed script, not by the agent."""
        self._connection.executemany(
            "INSERT INTO categories (category_id, name, aliases) VALUES (?, ?, ?)",
            [(c.category_id, c.name, c.aliases) for c in categories],
        )

    def insert_metric_points(self, points: list[MetricPoint]) -> None:
        """Bulk-insert daily metric values, one upsert per (category, date, metric).

        Used only by the mock-data seed script. `metric_key` values come
        from `mock_data.py`, which only ever generates points for metrics
        in `metrics.METRICS` — still validated here via `get_metric` so a
        bad key fails loudly instead of silently writing to a nonexistent
        column.
        """
        by_category_and_date: dict[tuple[int, date], dict[str, float]] = {}
        for point in points:
            get_metric(point.metric_key)
            key = (point.category_id, point.date)
            by_category_and_date.setdefault(key, {})[point.metric_key] = point.value

        metric_keys = [metric.key for metric in METRICS]
        columns_sql = ", ".join(metric_keys)
        placeholders_sql = ", ".join("?" for _ in metric_keys)
        update_sql = ", ".join(f"{key} = EXCLUDED.{key}" for key in metric_keys)
        # Column names below (`columns_sql`, `update_sql`) come only from `METRICS`,
        # a fixed internal registry — never from caller input — so this is safe DDL/DML
        # column assembly, not the injection risk S608 flags for value interpolation.
        query = (
            "INSERT INTO category_daily_metrics "  # noqa: S608
            f"(category_id, date, {columns_sql}) "
            f"VALUES (?, ?, {placeholders_sql}) "
            "ON CONFLICT (category_id, date) DO UPDATE SET "
            f"{update_sql}"
        )

        rows = [
            (
                category_id,
                snapshot_date,
                *(values.get(key) for key in metric_keys),
            )
            for (category_id, snapshot_date), values in by_category_and_date.items()
        ]
        self._connection.executemany(query, rows)
