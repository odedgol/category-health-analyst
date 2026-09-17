# Guide 01 — Product Definition and Domain Thinking

## Goal of this guide

Before writing Python, define exactly what the system is supposed to understand and answer.

This is not paperwork. It prevents the most expensive kind of confusion: building a technically impressive system around ambiguous business concepts.

At the end of this guide, we should know:

- Which questions are supported
- Which questions require clarification
- What each metric means
- What a site ID means
- What information is required to answer a question
- Which definitions are still open

No application code is written in this guide.

## Why we start here

An assistant can fail even when every line of code is valid.

For example, the phrase “image percentage” could mean:

```text
products with at least one image / all active products
```

or:

```text
total images / total products
```

Those are different business metrics. If we do not define the meaning first, the LLM, database schema, analytics code, and answer formatting may all make different assumptions.

The first architectural lesson is:

> Business definitions must be explicit before technical implementation begins.

## The product in one sentence

The Category Health Analyst answers questions about category-quality metrics for a specific eBay site and time period, and explains changes only when the available data and evidence support an explanation.

## What the first version supports

The first version supports:

- One category
- One or more selected metrics
- One eBay site or a comparison of two sites
- A snapshot at a point in time
- A date range or trend
- A comparison between two periods
- A request to explain a change
- Follow-up questions that modify the previous query

The first version does not support arbitrary questions about the entire business, arbitrary SQL, or unsupported causal claims.

## Site domain

The project uses eBay marketplace/site identifiers, not a self-invented country numbering system.

Examples:

| Site ID | Site | Common user expressions |
|---:|---|---|
| 0 | US | US, USA, United States, America |
| 2 | Canada | Canada, CA |
| 3 | UK | UK, United Kingdom, Britain |
| 15 | Australia | Australia, AU |
| 77 | Germany | Germany, German, Deutschland, DE |

The full catalog will be loaded statically from the official eBay reference. The LLM may help interpret a phrase, but it must resolve to one of the known static site IDs.

Important rule:

```text
Unknown site ≠ US
```

If the user says “Europe”, we should not silently choose Germany, the UK, or the US. We should ask which supported site they mean.

## Metric domain

The first five metrics are:

### 1. Image coverage percentage

Provisional meaning:

```text
products with at least one image / active products × 100
```

This definition must be confirmed before database implementation.

### 2. Image count

At product level, this is the total number of images attached to one active product. A product may have zero, one, two, or more images.

At aggregate level, this can be summed for a category and eBay site ID. The database must preserve the difference between a product-level image count and a category/site total.

### 3. Aligned aspects count

The number of taxonomy aspects that are aligned.

### 4. Misaligned aspects count

The number of taxonomy aspects that are misaligned.

### 5. Aligned and misaligned aspect percentages

The source also provides percentages for aligned and misaligned aspects. Their denominator must be documented explicitly before implementation.

### 6. Has title

Whether a product has a title. This is a boolean value.

## Example questions

These are the first questions our system should eventually support:

1. “What was the image coverage percentage for Laptop Chargers in the US last week?”
2. “How many images did Germany have for Laptop Chargers yesterday?”
3. “Compare taxonomy-aligned products in Germany and the US.”
4. “How many products were not aligned to taxonomy in the UK last month?”
5. “What percentage of products had a title in the US?”
6. “Show the image count trend for the last 30 days.”
7. “Why did image coverage decline in Germany?”
8. “What about the US?”
9. “Compare it with Germany.”

## Questions requiring clarification

The system should ask for clarification when the meaning is not safe to infer.

Examples:

| User question | Why clarification is needed |
|---|---|
| “How is the category doing?” | Category and metric are missing |
| “What happened in Europe?” | Europe is not one supported eBay site |
| “Show me the image metric.” | Could mean image count or image coverage |
| “How many titles?” | Count versus percentage is undefined |
| “What happened around the migration?” | No date or incident is identified |

The clarification should be specific. Instead of:

```text
Please clarify.
```

prefer:

```text
Do you mean image count or image coverage percentage? I can also check the trend for a specific site and date range.
```

## The information required by a query

Most analytical questions require some version of these fields:

```text
intent
metric
category
site
date range
comparison range, if applicable
```

For example:

```text
Question:
What was the image coverage percentage for Laptop Chargers in the US last week?

Required interpretation:
intent = trend or lookup
metric = image_coverage_percentage
category = Laptop Chargers
site = 0
date range = previous calendar week
comparison range = none
```

This list will later become the foundation of `AnalyticsQuerySpec`.

## Decisions still open

Before building the repository, we need answers to these questions:

1. Is `image_count` stored as a raw integer, a bucket such as `0`, `1`, `2+`, or both?
2. Does the source provide taxonomy data per product, or already aggregated?
3. What exactly does LMD contain: a date, timestamp, or source-system version?
4. When several updates exist on one day, should a query return the latest update or a full intra-day history?
5. What categories exist in the initial demonstration dataset?

These are not implementation details. They define the data model.

The following decisions are now confirmed:

- Only active products are counted for image coverage.
- Image count can be zero, one, two, or more per product.
- Image count can also be aggregated for a category and site ID.
- Taxonomy data includes aligned and misaligned aspect counts and percentages.
- `has_title` is boolean.
- Data is updated daily.
- A category/site can have multiple updates on the same day.
- Each update has an LMD that must be preserved.
- Aligned and misaligned aspect percentages use total aspects as the denominator.

```text
aligned_aspects_percentage = aligned_aspects_count / total_aspects × 100
misaligned_aspects_percentage = misaligned_aspects_count / total_aspects × 100
```

## Acceptance criteria for Guide 01

Guide 01 is complete when we can explain, in our own words:

- The difference between a marketplace site ID and a generic country
- The exact meaning of each initial metric
- Why aliases belong in a catalog
- Why ambiguous questions require clarification
- Which fields are required to execute an analytical query
- Which definitions are still unsafe to implement
- Why multiple same-day updates mean that LMD belongs in the domain model

## What we will build next

In Guide 02, we will turn these concepts into a small, dependency-light domain model.

We will begin with plain Python and Pydantic models. We will not add an LLM, database, LangGraph, RAG, or UI yet.
