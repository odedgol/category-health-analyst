"""DuckDB adapter implementing the metrics repository contract."""

from datetime import UTC, datetime

import duckdb

from category_health.domain.models import CategorySiteMetrics, DateRange


class DuckDbMetricsRepository:
    """Persist and query aggregate category/site metric updates in DuckDB."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._connection = connection
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS category_site_metric_updates (
                category_id INTEGER NOT NULL,
                site_id INTEGER NOT NULL,
                observed_date DATE NOT NULL,
                last_modified_at TIMESTAMP NOT NULL,
                active_product_count INTEGER NOT NULL,
                image_count INTEGER NOT NULL,
                has_title BOOLEAN NOT NULL,
                image_coverage_percentage DECIMAL(10, 4) NOT NULL,
                aligned_aspects_count INTEGER NOT NULL,
                misaligned_aspects_count INTEGER NOT NULL,
                aligned_aspects_percentage DECIMAL(10, 4) NOT NULL,
                misaligned_aspects_percentage DECIMAL(10, 4) NOT NULL,
                PRIMARY KEY (
                    category_id,
                    site_id,
                    observed_date,
                    last_modified_at
                )
            )
            """
        )

    def add_update(self, update: CategorySiteMetrics) -> None:
        """Insert one update, rejecting an exact duplicate identity."""

        try:
            self._connection.execute(
                """
                INSERT INTO category_site_metric_updates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    update.category_id,
                    update.site_id,
                    update.observed_date,
                    update.last_modified_at.astimezone(UTC).replace(tzinfo=None),
                    update.active_product_count,
                    update.image_count,
                    update.has_title,
                    update.image_coverage_percentage,
                    update.aligned_aspects_count,
                    update.misaligned_aspects_count,
                    update.aligned_aspects_percentage,
                    update.misaligned_aspects_percentage,
                ],
            )
        except duckdb.ConstraintException as error:
            raise ValueError("Duplicate metric update") from error

    def list_updates(
        self, category_id: int, site_id: int, date_range: DateRange
    ) -> list[CategorySiteMetrics]:
        rows = self._connection.execute(
            """
            SELECT
                category_id,
                site_id,
                observed_date,
                last_modified_at,
                active_product_count,
                image_count,
                has_title,
                image_coverage_percentage,
                aligned_aspects_count,
                misaligned_aspects_count,
                aligned_aspects_percentage,
                misaligned_aspects_percentage
            FROM category_site_metric_updates
            WHERE category_id = ?
              AND site_id = ?
              AND observed_date BETWEEN ? AND ?
            ORDER BY observed_date, last_modified_at
            """,
            [category_id, site_id, date_range.start, date_range.end],
        ).fetchall()
        return [self._to_model(row) for row in rows]

    def latest_per_day(
        self, category_id: int, site_id: int, date_range: DateRange
    ) -> list[CategorySiteMetrics]:
        rows = self._connection.execute(
            """
            WITH ranked AS (
                SELECT
                    category_id,
                    site_id,
                    observed_date,
                    last_modified_at,
                    active_product_count,
                    image_count,
                    has_title,
                    image_coverage_percentage,
                    aligned_aspects_count,
                    misaligned_aspects_count,
                    aligned_aspects_percentage,
                    misaligned_aspects_percentage,
                    ROW_NUMBER() OVER (
                        PARTITION BY observed_date
                        ORDER BY last_modified_at DESC
                    ) AS row_number
                FROM category_site_metric_updates
                WHERE category_id = ?
                  AND site_id = ?
                  AND observed_date BETWEEN ? AND ?
            )
            SELECT
                category_id,
                site_id,
                observed_date,
                last_modified_at,
                active_product_count,
                image_count,
                has_title,
                image_coverage_percentage,
                aligned_aspects_count,
                misaligned_aspects_count,
                aligned_aspects_percentage,
                misaligned_aspects_percentage
            FROM ranked
            WHERE row_number = 1
            ORDER BY observed_date
            """,
            [category_id, site_id, date_range.start, date_range.end],
        ).fetchall()
        return [self._to_model(row) for row in rows]

    def latest_update(self, category_id: int, site_id: int) -> CategorySiteMetrics | None:
        row = self._connection.execute(
            """
            SELECT
                category_id,
                site_id,
                observed_date,
                last_modified_at,
                active_product_count,
                image_count,
                has_title,
                image_coverage_percentage,
                aligned_aspects_count,
                misaligned_aspects_count,
                aligned_aspects_percentage,
                misaligned_aspects_percentage
            FROM category_site_metric_updates
            WHERE category_id = ?
              AND site_id = ?
            ORDER BY last_modified_at DESC
            LIMIT 1
            """,
            [category_id, site_id],
        ).fetchone()
        return None if row is None else self._to_model(row)

    def available_date_range(self, category_id: int, site_id: int) -> DateRange | None:
        row = self._connection.execute(
            """
            SELECT MIN(observed_date), MAX(observed_date)
            FROM category_site_metric_updates
            WHERE category_id = ? AND site_id = ?
            """,
            [category_id, site_id],
        ).fetchone()
        if row is None or row[0] is None or row[1] is None:
            return None
        return DateRange(start=row[0], end=row[1])

    @staticmethod
    def _to_model(row: tuple[object, ...]) -> CategorySiteMetrics:
        last_modified_at = row[3]
        if isinstance(last_modified_at, datetime) and last_modified_at.tzinfo is None:
            last_modified_at = last_modified_at.replace(tzinfo=UTC)
        return CategorySiteMetrics(
            category_id=int(row[0]),
            site_id=int(row[1]),
            observed_date=row[2],
            last_modified_at=last_modified_at,
            active_product_count=int(row[4]),
            image_count=int(row[5]),
            has_title=bool(row[6]),
            image_coverage_percentage=row[7],
            aligned_aspects_count=int(row[8]),
            misaligned_aspects_count=int(row[9]),
            aligned_aspects_percentage=row[10],
            misaligned_aspects_percentage=row[11],
        )
