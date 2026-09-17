# Guide 04 — DuckDB Repository Adapter

## Goal of this guide

In Guide 03, the in-memory repository proved the business behavior:

- Preserve multiple updates
- Filter by category, site, and date range
- Select the latest LMD per day

Now we will store the same records in DuckDB.

The important rule is:

> Adding a database must not change the meaning of the application.

The application depends on `MetricsRepository`, not on DuckDB directly.

## Why DuckDB

DuckDB is a good fit for this educational project because:

- It is an analytical database.
- It runs locally inside the process.
- It supports SQL window functions.
- It is easy to test with an in-memory database.
- It does not require a separate database server.

We are using DuckDB as a storage adapter, not as the domain model.

## Table design

The table represents one aggregate update:

```sql
CREATE TABLE category_site_metric_updates (
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
    PRIMARY KEY (category_id, site_id, observed_date, last_modified_at)
)
```

The primary key reflects the version-1 update identity:

```text
category_id + site_id + observed_date + last_modified_at
```

This allows two updates on the same day as long as their LMD values differ.

The application treats LMD as UTC. DuckDB stores it as a timestamp and the adapter normalizes the value back to an aware UTC `datetime` when constructing the domain model.

## Latest update per day

The SQL equivalent of the in-memory grouping logic is a window function:

```sql
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY observed_date
            ORDER BY last_modified_at DESC
        ) AS row_number
    FROM category_site_metric_updates
    WHERE category_id = ?
      AND site_id = ?
      AND observed_date BETWEEN ? AND ?
)
SELECT *
FROM ranked
WHERE row_number = 1
ORDER BY observed_date
```

`ROW_NUMBER()` creates a ranking inside each calendar day. The newest LMD gets rank 1.

## Parameterized SQL

User-provided values must be parameters:

```sql
WHERE category_id = ?
  AND site_id = ?
  AND observed_date BETWEEN ? AND ?
```

We must never build SQL by concatenating category IDs, site IDs, or dates into a string.

## Adapter boundary

The DuckDB adapter is responsible for:

- Creating the table
- Binding parameters
- Converting database rows into domain models
- Translating duplicate-key errors into a clear application error

The adapter is not responsible for:

- Resolving site synonyms
- Parsing questions
- Deciding whether a metric is relevant
- Explaining trends

## Acceptance criteria

The DuckDB repository is complete when it proves the same behavior as the in-memory repository:

- Same-day updates are preserved.
- Exact duplicates are rejected.
- Date ranges are inclusive.
- Category/site filters are enforced.
- Latest LMD per day is selected correctly.
- Returned rows are domain models, not raw tuples.

## What we will build next

After this guide, we will create the static metric and site catalogs. Those catalogs will be used by deterministic resolution before we introduce an LLM.
