"""Load and safely resolve the supplied category ID/name export."""

import re
from dataclasses import dataclass
from pathlib import Path

from category_health.catalogs.catalogs import normalize_phrase

_CATEGORY_LINE = re.compile(r"^\s*(?P<name>.+?)\s+\|\s+ID:\s*(?P<category_id>\d+)\s*$")


@dataclass(frozen=True)
class CategoryDefinition:
    category_id: int
    name: str


class CategoryCatalog:
    """Resolve category IDs and names without overwriting duplicate names."""

    def __init__(self, categories: tuple[CategoryDefinition, ...]) -> None:
        self.categories = categories
        self._by_id = {category.category_id: category for category in categories}
        self._by_name: dict[str, list[CategoryDefinition]] = {}
        for category in categories:
            normalized = normalize_phrase(category.name)
            self._by_name.setdefault(normalized, []).append(category)

    def resolve_by_id(self, category_id: int) -> CategoryDefinition | None:
        return self._by_id.get(category_id)

    def candidates_by_name(self, name: str) -> tuple[CategoryDefinition, ...]:
        return tuple(self._by_name.get(normalize_phrase(name), []))

    def resolve(self, mention: str) -> CategoryDefinition | None:
        """Return one category only when the mention is unambiguous."""

        normalized = normalize_phrase(mention)
        if normalized.isdigit():
            return self.resolve_by_id(int(normalized))

        candidates = self.candidates_by_name(mention)
        return candidates[0] if len(candidates) == 1 else None


def load_category_catalog(path: Path) -> CategoryCatalog:
    """Parse category records and ignore non-record export UI lines."""

    categories: list[CategoryDefinition] = []
    seen_ids: set[int] = set()
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            match = _CATEGORY_LINE.match(line.rstrip("\n"))
            if match is None:
                continue

            category_id = int(match.group("category_id"))
            if category_id in seen_ids:
                raise ValueError(f"Duplicate category ID {category_id} on line {line_number}")
            seen_ids.add(category_id)
            categories.append(
                CategoryDefinition(category_id=category_id, name=match.group("name").strip())
            )

    if not categories:
        raise ValueError(f"No category records found in {path}")
    return CategoryCatalog(tuple(categories))
