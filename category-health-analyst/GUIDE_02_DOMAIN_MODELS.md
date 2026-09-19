# Guide 02 — Designing the Domain Models

## Goal of this guide

In Guide 01, we defined the business language of the application.

Now we translate that language into explicit domain objects. These objects will become the stable foundation for the repository, analytics engine, query planner, and answer layer.

We will not start with database tables. We will first model the meaning of the data in plain application terms.

## Why domain models come before database models

A database schema answers:

> How should data be stored?

A domain model answers:

> What does this data mean to the business?

Those questions are related, but they are not identical.

For example, the database may store a timestamp as a SQL `TIMESTAMP`, but the domain concept is an `ObservationUpdate` with a `last_modified_at` value that determines which update is newer.

If we start with tables, we may accidentally allow the storage format to define the business behavior.

## The data level

For the first version, all source values are already aggregated. We do not store product-level observations in this application.

### Stored category/site metrics

The upstream data process calculates and stores the metrics for one category and one eBay site. Our application reads this stored snapshot.

```text
CategorySiteMetrics
├── category_id
├── site_id
├── active_product_count
├── image_coverage_percentage
├── image_count
├── aligned_aspects_count
├── misaligned_aspects_count
├── aligned_aspects_percentage
├── misaligned_aspects_percentage
└── has_title
```

The upstream process calculates image coverage before storing it:

```text
image_coverage_percentage =
products_with_images_count / active_product_count × 100
```

The application uses the stored `image_coverage_percentage` value to answer questions. It does not repeat the calculation during every query.

`image_count` and `has_title` are also aggregated values supplied by the source. We do not reinterpret them as individual product records.

### Update ordering

The same category and site can receive multiple updates on the same day.

Therefore, a metric record needs more than a calendar date. For the first version, the LMD value is enough to identify and order the latest update.

```text
ObservationUpdate
├── category_id
├── site_id
├── observed_at
└── last_modified_at
```

The `last_modified_at` value lets us order updates and determine which record is the latest.

We will not add a separate `update_id` yet. A separate ID is useful only if two updates can have the same LMD, or if the source provides another stable identifier that is needed for auditing.

## Why a calendar date is not enough

Suppose the system receives:

| Category | Site | Date | LMD | Image coverage |
|---|---|---|---|---:|
| Laptop Chargers | Germany | 2026-09-10 | 08:00 | 72.0% |
| Laptop Chargers | Germany | 2026-09-10 | 14:00 | 69.5% |

If we store only `2026-09-10`, we lose the ability to answer:

- Which update was latest?
- When did the change appear?
- Was the value corrected later on the same day?
- What did the system know at a specific time?

This is why LMD belongs in the domain model.

## Proposed value objects

We should model these concepts explicitly:

```python
class SiteDefinition:
    site_id: int
    name: str
    country: str
    abbreviation: str
    aliases: tuple[str, ...]
```

`SiteDefinition` belongs to the static site catalog rather than the stored metric
domain model. Observations reference it by `site_id`.

```python
class DateRange(BaseModel):
    start: date
    end: date
```

class CategorySiteMetrics(BaseModel):
    category_id: int
    site_id: int
    observed_at: datetime
    last_modified_at: datetime
    active_product_count: int
    image_coverage_percentage: Decimal
    image_count: int
    aligned_aspects_count: int
    misaligned_aspects_count: int
    aligned_aspects_percentage: Decimal
    misaligned_aspects_percentage: Decimal
    has_title: bool
```

## Important validation rules

The domain model should reject invalid business data early.

### Counts cannot be negative

```text
image_count >= 0
aligned_aspects_count >= 0
misaligned_aspects_count >= 0
active_product_count >= 0
```

### Percentages must be valid

```text
0 <= percentage <= 100
```

### Image coverage needs a denominator

If `active_product_count == 0`, this project defines image coverage as `0%`.

This is a deliberate product decision. It means:

```text
no active products → 0% image coverage
```

The distinction between “not applicable” and `0%` can be added later if the business requires it. For the first version, the simpler rule is more useful and should be applied consistently.

### Taxonomy percentages must agree with counts

If total aspects are greater than zero:

```text
aligned_aspects_percentage + misaligned_aspects_percentage ≈ 100
```

The model should allow a small rounding tolerance, for example `0.01` percentage points.

### LMD ordering must be explicit

The system should not silently accept an update where:

```text
last_modified_at < observed_at
```

unless the source contract explicitly allows that situation.

## A key design choice: source-calculated values versus query-calculated values

The upstream process calculates the metrics before writing them to the database. Our analyst reads those stored values.

Stored values include:

- `image_coverage_percentage`
- `image_count`
- `has_title`
- `aligned_aspects_count`
- `misaligned_aspects_count`
- `aligned_aspects_percentage`
- `misaligned_aspects_percentage`

Our application may calculate temporary analytical values from stored metrics, such as:

- Change between two updates
- Absolute delta
- Relative delta
- Trend direction
- Before/after comparison

### Simple explanation

A stored metric is a value produced by the upstream data process and saved in the database.

Example:

```text
image_coverage_percentage = 72
image_count = 180
has_title = true
aligned_aspects_count = 450
misaligned_aspects_count = 50
```

A query-derived value is calculated by our analyst from stored metrics.

Example:

```text
previous_image_coverage = 72%
current_image_coverage = 69%
change = -3 percentage points
```

The important boundary is:

```text
Upstream process:
product data → stored category/site metrics

Our analyst:
stored metrics → comparison, trend, or explanation
```

The analyst must not silently replace the stored metric definitions with a new formula. It may validate values when the necessary inputs are available, but the stored values are the source of truth for the first version.

## What belongs in the domain layer

The domain layer should contain:

- Business models
- Validation rules
- Pure calculation functions
- Domain-specific exceptions

It should not contain:

- SQL
- DuckDB imports
- Streamlit imports
- Chroma imports
- LangGraph imports
- OpenAI client calls

This keeps the most important business logic easy to test and explain.

## Exercise before implementation

For this example:

```text
Category: Laptop Chargers
Site: Germany, SiteID 77
Active products: 100
Products with at least one image: 72
Total images: 180
Aligned aspects: 450
Misaligned aspects: 50
Products with titles: 96
```

Assume the upstream process has already calculated and stored these values:

```text
image_coverage_percentage = 72%
aligned_aspects_percentage = 90%
misaligned_aspects_percentage = 10%
```

Then answer:

1. Which values are stored metrics from the upstream process?
2. Which values would our analyst derive when comparing this update with another update?
3. What happens if active products are zero?
4. Why is LMD useful?
5. Why are we not adding a separate update ID yet?

## Acceptance criteria for Guide 02

Before writing the models, we should be able to explain:

- Why the first version stores only category/site aggregates
- Why multiple same-day updates require LMD ordering
- Why LMD is part of the domain
- The difference between source-calculated metrics and query-calculated analysis
- Why this project deliberately defines zero active products as zero percent
- Which validation rules protect data quality

## What we will build next

The domain module has now been implemented. The next guide will design the repository around these aggregate update rows:

```text
src/category_health/domain/models.py
src/category_health/domain/calculations.py
tests/unit/domain/
```

The implementation will use Python and Pydantic only. We will write tests before connecting a repository or an LLM.
