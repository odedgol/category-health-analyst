# Guide 03 — Repository Design and Time-Based Queries

## Goal of this guide

We now have an aggregate domain record:

```text
category + site + observed date + LMD + stored metrics
```

This guide explains how the application reads those records without knowing whether they come from memory, DuckDB, or another database.

## Why we start with an in-memory repository

If we start with SQL immediately, it becomes difficult to tell whether a bug comes from:

- The business rule
- The query logic
- The database syntax
- The database driver

An in-memory repository lets us test the business behavior first.

The repository will be replaceable later:

```text
Agent / analytics code
        ↓
MetricsRepository interface
        ↓
InMemoryMetricsRepository now
DuckDBMetricsRepository later
```

## Repository responsibilities

The repository is responsible for:

- Storing aggregate metric updates
- Returning updates for a category/site/date range
- Selecting the latest LMD for one day
- Selecting the latest update per day
- Selecting the latest known update overall
- Rejecting an exact duplicate update

The repository is not responsible for:

- Understanding natural language
- Choosing a metric based on synonyms
- Explaining why a metric changed
- Calling an LLM
- Writing the final answer

## Exact update identity

For version 1, an update is identified by:

```text
(category_id, site_id, observed_date, last_modified_at)
```

Two rows with different LMD values are different updates, even if all metric values are identical.

Two rows with the same four identity fields are duplicates and should not be silently inserted twice.

## Daily selection rule

When the user asks for a daily trend, we should not return every update automatically.

The rule is:

```text
For each observed_date:
    select the row with the greatest last_modified_at
```

Example:

```text
2026-09-10 08:00 → 72%
2026-09-10 14:00 → 69%
2026-09-11 09:00 → 68%
```

Daily view:

```text
2026-09-10 → 69%
2026-09-11 → 68%
```

The earlier 08:00 row remains stored and can still be used for an intraday investigation.

## Date-range behavior

Date ranges are inclusive.

For a three-day request:

```text
start = 2026-09-08
end   = 2026-09-10
```

The repository returns updates whose `observed_date` is between those dates, including both boundaries.

The analytics layer can then compare:

```text
first daily value → last daily value
```

For a thirty-day request, exactly the same rule applies. Only the range changes.

## Repository contract

The application should depend on a small protocol rather than a concrete storage class:

```python
class MetricsRepository(Protocol):
    def add_update(self, update: CategorySiteMetrics) -> None: ...

    def list_updates(
        self,
        category_id: int,
        site_id: int,
        date_range: DateRange,
    ) -> list[CategorySiteMetrics]: ...

    def latest_per_day(
        self,
        category_id: int,
        site_id: int,
        date_range: DateRange,
    ) -> list[CategorySiteMetrics]: ...
```

The protocol describes what the application needs, not how storage works.

## Acceptance criteria

The repository implementation is correct when it can prove that:

- Multiple updates on one day are preserved.
- The latest LMD is selected for daily analysis.
- Date ranges are inclusive.
- Updates from another category or site do not leak into results.
- Duplicate exact updates are rejected.
- Results are returned in chronological order.

## What we are intentionally not doing yet

- No DuckDB
- No SQL
- No LLM
- No natural-language parsing
- No trend explanation
- No RAG

The next guide will add a DuckDB adapter that implements the same repository contract.
