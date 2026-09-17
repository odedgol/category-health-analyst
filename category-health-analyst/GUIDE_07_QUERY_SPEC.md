# Guide 07 — The Structured Query Specification

## Goal of this guide

We now have:

- Stored aggregate metrics
- A repository
- Static site and metric catalogs
- A real category catalog

The next problem is representing a user request in a stable, validated form.

The answer is `AnalyticsQuerySpec`.

## Why we need an intermediate representation

The repository should never receive this:

```text
"What happened with image coverage for Antiques in Germany last week?"
```

It should receive structured data:

```text
intent = explain_change
metric_ids = [image_coverage_percentage]
category_id = 20081
site_ids = [77]
date_range = last calendar week
comparison_range = none
```

This creates a boundary:

```text
Natural language
       ↓
AnalyticsQuerySpec
       ↓
Planner and repository
```

The LLM, when introduced later, will help create the first object. It will not control the repository directly.

## Query intents

The first version supports these intents:

```text
snapshot
trend
compare_periods
compare_sites
explain_change
```

Examples:

| Question | Intent |
|---|---|
| “What is the current image count?” | snapshot |
| “Show image coverage for the last 30 days.” | trend |
| “Compare last week with the week before.” | compare_periods |
| “Compare Germany with the US.” | compare_sites |
| “Why did image coverage decline?” | explain_change |

## Required and optional fields

Every query needs:

- One intent
- At least one metric
- One category
- At least one site

Dates depend on the intent:

- A snapshot may use the latest available update.
- A trend needs a date range.
- A period comparison needs two date ranges.
- An explanation may initially have no date and require change detection later.

## Unresolved fields

The specification should be able to represent an incomplete request safely:

```text
unresolved_fields = ["category", "date_range"]
```

An incomplete specification must not be executed. The clarification layer will use these fields to ask a focused question.

## Confidence

Confidence belongs to interpretation, not to database results.

For the first version, confidence is a number between `0.0` and `1.0`.

Later, we can store field-level confidence. For now, the query is executable only when required fields are resolved and no unresolved fields remain.

## Acceptance criteria

- A complete query can be created without any LLM.
- Missing required fields are represented explicitly.
- Unsupported combinations are rejected.
- A period comparison requires two date ranges.
- A site comparison requires exactly two site IDs.
- Metric IDs are validated against the static metric catalog before execution.
- The repository receives only validated structured data.

## What we will build next

The next guide will build deterministic reference resolution: category names, site mentions, and metric phrases will be converted into the IDs used by `AnalyticsQuerySpec`.
