# Initial Domain Decisions

This document records the first product decisions before implementation begins.

## Site identifiers

Sites are based on eBay Trading API `SiteCodeType` values.

Authoritative source:

<https://developer.ebay.com/devzone/xml/docs/reference/ebay/types/sitecodetype.html>

The source lists eBay marketplace/site values, their site IDs, abbreviations, and currencies. The project will store this information statically in a versioned catalog and use it for deterministic site resolution.

Initial examples:

| Site ID | Canonical name | Country / marketplace | Example aliases |
|---:|---|---|---|
| 0 | US | United States | US, USA, United States, America, ebay.com |
| 2 | Canada | Canada | Canada, CA, ebay.ca |
| 3 | UK | United Kingdom | UK, United Kingdom, Britain, ebay.co.uk |
| 15 | Australia | Australia | Australia, AU, ebay.com.au |
| 77 | Germany | Germany | Germany, German, Deutschland, DE, ebay.de |

The complete catalog will be added from the official source before site-resolution implementation.

Important distinction: these are eBay site/marketplace identifiers. They should not automatically be treated as generic geographic regions. Different marketplace variants can exist for the same country or language.

## Initial metric scope

Only five factors are in scope initially:

| Metric ID | Human meaning | Initial status |
|---|---|---|
| `image_coverage_percentage` | Percentage of active products with at least one image | Defined |
| `image_count` | Number of images on a product, and aggregate total by category/site | Defined |
| `aligned_aspects_count` | Number of taxonomy aspects aligned | Defined |
| `misaligned_aspects_count` | Number of taxonomy aspects misaligned | Defined |
| `aligned_aspects_percentage` | Percentage of taxonomy aspects aligned | Defined |
| `misaligned_aspects_percentage` | Percentage of taxonomy aspects misaligned | Defined |
| `has_title` | Whether a product has a title | Boolean |

## Metric-resolution synonyms

| Metric | Synonyms |
|---|---|
| Image coverage percentage | image percentage, image coverage, percentage with images |
| Image count | number of images, images count, total images, images per product |
| Aligned aspects count | aligned aspects, taxonomy aligned, aligned to taxonomy |
| Misaligned aspects count | misaligned aspects, taxonomy mismatch, not aligned taxonomy |
| Aligned aspects percentage | aligned percentage, percentage aligned, taxonomy alignment percentage |
| Misaligned aspects percentage | misaligned percentage, percentage misaligned, taxonomy mismatch percentage |
| Has title | title exists, has a title, product title present |

Synonyms are input vocabulary only. They do not create additional metrics.

## Questions in the first slice

The first slice should understand questions about:

- A metric for one category, site, and date range
- A comparison between two periods
- A comparison between two supported sites
- A trend over time
- A request to explain a change
- A follow-up that changes only the site, metric, or date range

Examples:

1. “What was the image coverage percentage for Laptop Chargers in the US last week?”
2. “How many images did Germany have for Laptop Chargers yesterday?”
3. “Compare taxonomy-aligned products in Germany and the US.”
4. “How many products were not aligned to taxonomy in the UK last month?”
5. “What percentage of products had a title in the US?”
6. “Show the image count trend for the last 30 days.”
7. “Why did image coverage decline in Germany?”
8. “What about the US?”
9. “Compare it with Germany.”

## Open decisions before database design

These must be resolved before implementing the repository schema:

1. Whether `image_count` is stored as a raw integer, a bucket such as `0`, `1`, `2+`, or both at product and aggregate level.
2. Whether taxonomy aspect counts are stored per product and aggregated later, or arrive already aggregated.
3. Whether the LMD value is a date, timestamp, or source-system version identifier.
4. When several updates exist on one day, whether a query returns the latest update or a full intra-day history.

## Confirmed data behavior

- Only active products are included in image coverage.
- Image coverage is calculated per category and eBay site ID.
- A product can have zero, one, two, or more images.
- Image count is meaningful at product level and can also be aggregated for a category/site combination.
- Taxonomy data includes aligned-aspect count, misaligned-aspect count, and aligned/misaligned percentages.
- `has_title` is boolean.
- Source data is updated daily.
- A category/site can receive multiple updates on the same day.
- Each update carries an LMD (last-modified value), which is sufficient for ordering updates in the first version and must be preserved for reproducibility.
- Aligned and misaligned aspect percentages use total aspects as the denominator:
  - `aligned_aspects_percentage = aligned_aspects_count / total_aspects * 100`
  - `misaligned_aspects_percentage = misaligned_aspects_count / total_aspects * 100`

The two percentages should therefore add up to 100% when the source contains only aligned and misaligned aspects.

The repository must distinguish product-level observations, category/site aggregates, and LMD. We must not collapse multiple same-day updates until the desired query behavior is explicitly defined.

For the first version, LMD is the update identity. A separate `update_id` will be introduced only if the source allows duplicate LMD values or if another stable identity becomes necessary.
# September 12 update — Mock-first production preparation

Keep reproducible mock aggregates while preparing production behavior. Real database
integration is optional and deferred behind MetricsRepository. Period comparisons
currently mean latest snapshot in each period, not daily sums or averages; site
comparisons match observed dates. See GUIDE_16_COMPARISONS_CONVERSATION_AUDIT.md.
