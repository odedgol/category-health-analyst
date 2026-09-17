# Guide 05 — Static Site and Metric Catalogs

## Goal of this guide

The application needs to understand two closed vocabularies:

1. eBay sites and their SiteIDs
2. Supported category-health metrics and their synonyms

These are business definitions, not things the LLM should invent.

## Why static catalogs matter

Suppose a user writes:

```text
Germany
Deutschland
DE
ebay.de
77
```

All of these should resolve deterministically to SiteID `77`.

Similarly:

```text
image percentage
image coverage
percentage with images
```

should resolve to the same registered metric.

The LLM may help extract a phrase, but the catalog decides whether that phrase is valid.

## Site catalog design

Each site record contains:

```yaml
site_id: 77
name: Germany
country: Germany
abbreviation: DE
aliases:
  - Germany
  - German
  - Deutschland
  - DE
  - ebay.de
```

The catalog is based on the official eBay `SiteCodeType` reference and is versioned inside the repository.

The catalog is not fetched at runtime. This makes resolution:

- Reproducible
- Testable offline
- Fast
- Reviewable
- Independent of model behavior

## Metric catalog design

Each metric record contains:

```yaml
id: image_coverage_percentage
display_name: Image coverage percentage
unit: percentage
aliases:
  - image percentage
  - image coverage
  - percentage with images
```

The catalog should also document whether the metric is a count, percentage, or boolean.

## Normalization

Before matching a phrase, deterministic normalization should:

- Trim whitespace
- Convert to lowercase
- Collapse repeated spaces
- Normalize harmless punctuation differences

For example:

```text
"  Deutschland " → "deutschland"
"Image-Coverage" → "image coverage"
```

Normalization must not use fuzzy matching yet. Exact aliases are easier to reason about and test.

## Unknown and ambiguous values

If a phrase does not match the catalog:

```text
resolve("Europe") → None
```

The system must ask for clarification. It must not default to the US.

If two aliases resolve to different records, catalog loading should fail immediately. An ambiguous catalog is a configuration error.

## Acceptance criteria

- SiteID `77` resolves from `Germany`, `Deutschland`, `DE`, and `ebay.de`.
- SiteID `0` resolves from `US`, `USA`, and `United States`.
- Metric synonyms resolve to the correct metric ID.
- Unknown sites return no match.
- Unknown metrics return no match.
- Duplicate aliases are rejected when the catalog loads.
- Catalog tests require no network access.

## What we will build next

The next guide will introduce categories and deterministic category resolution. Only after deterministic resolution works will we discuss how an LLM may help with phrases that do not match exactly.
