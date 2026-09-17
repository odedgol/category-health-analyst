# Guide 06 — Loading the Real Category Catalog

## Goal of this guide

The project now uses the real category map supplied by the user.

The source contains category names and IDs in this format:

```text
Antiques | ID: 20081
Architectural & Garden | ID: 4707
```

The catalog contains more than twenty thousand records.

## What the source gives us

The map gives us:

- Stable category IDs
- Category names
- A large production-like catalog

The map does not currently give us:

- Parent category paths
- Hierarchy
- Explicit aliases
- Language translations
- Category status history

We should not invent those fields. We will add them only when the source provides them or the product explicitly defines them.

## Duplicate names are valid

Category names are not globally unique.

For example, the catalog contains multiple categories called `Armor` and `Bells` under different parts of the taxonomy.

Therefore:

```text
Category ID → always deterministic
Category name → deterministic only if unique
Duplicate name → clarification required
```

This is why a category resolver must not simply use:

```python
name_to_id[name] = category_id
```

That would silently overwrite one category with another.

Instead, we store:

```python
normalized_name → list[CategoryDefinition]
```

## Safe resolution behavior

```text
resolve("20081")       → Antiques / ID 20081
resolve("Antiques")    → Antiques / ID 20081
resolve("Armor")       → ambiguous; ask for clarification
resolve("Not a real category") → no match
```

The resolver must distinguish:

- No match
- One exact match
- Multiple exact matches

These are different user experiences.

## Why we keep the original source file

The original export is kept in `data/categories_source.txt` because it is an input artifact. The loader parses it into domain objects at startup or during catalog preparation.

Keeping the source makes it possible to:

- Rebuild the catalog
- Audit where a category ID came from
- Replace the export with a newer version
- Test the parser against the real format

## Acceptance criteria

- The source loads without duplicate IDs.
- More than twenty thousand category records are parsed.
- Category ID lookup works.
- Unique category-name lookup works.
- Duplicate names are returned as ambiguous.
- Unknown names return no match.
- No network call is needed.

## What we will build next

The next guide will connect category and metric resolution to a structured `QuerySpec`. That will be the first step toward understanding natural-language questions without executing any database query yet.
