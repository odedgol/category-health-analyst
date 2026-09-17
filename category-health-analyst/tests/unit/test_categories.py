from pathlib import Path

import pytest
from category_health.catalogs.categories import (
    CategoryCatalog,
    CategoryDefinition,
    load_category_catalog,
)

ROOT = Path(__file__).parents[2]


def test_real_category_export_loads_without_duplicate_ids() -> None:
    catalog = load_category_catalog(ROOT / "data" / "categories_source.txt")

    assert len(catalog.categories) > 20_000
    assert catalog.resolve("20081").name == "Antiques"


def test_unique_category_name_resolves() -> None:
    catalog = load_category_catalog(ROOT / "data" / "categories_source.txt")

    result = catalog.resolve("Antiques")

    assert result is not None
    assert result.category_id == 20081


def test_duplicate_category_name_is_ambiguous() -> None:
    catalog = load_category_catalog(ROOT / "data" / "categories_source.txt")

    assert catalog.resolve("Armor") is None
    assert len(catalog.candidates_by_name("Armor")) > 1


def test_unknown_category_has_no_match() -> None:
    catalog = load_category_catalog(ROOT / "data" / "categories_source.txt")

    assert catalog.resolve("Definitely Not A Category") is None


def test_duplicate_category_ids_are_rejected() -> None:
    path = ROOT / "data" / "duplicate_categories_test.txt"
    path.write_text("First | ID: 1\nSecond | ID: 1\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="Duplicate category ID"):
            load_category_catalog(path)
    finally:
        path.unlink()


def test_duplicate_names_are_kept_as_separate_candidates() -> None:
    catalog = CategoryCatalog(
        (
            CategoryDefinition(1, "Bells"),
            CategoryDefinition(2, "Bells"),
        )
    )

    assert [candidate.category_id for candidate in catalog.candidates_by_name("bells")] == [1, 2]
    assert catalog.resolve("bells") is None
