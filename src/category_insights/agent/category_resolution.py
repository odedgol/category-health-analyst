"""Category-mention resolution: a 4-handler Chain of Responsibility.

Unlike `sites.match_known_site` (a closed set of 5 regions — exact/alias
matching is enough, see its docstring), the category catalog is
open-ended and aliased, and a loosely-worded mention ("running shoes",
"sneaker") deserves a real fuzzy match. Four handlers, tried in order;
the first to return a `CategoryMatch` wins:

1. `ExactNameHandler` — case-insensitive exact match on `Category.name`.
2. `AliasHandler` — case-insensitive exact match on `Category.aliases`.
3. `SubstringHandler` — `mention` and a name/alias share one as a
   substring of the other (loosely worded, but still literal text).
4. `SemanticSearchHandler` — embedding similarity via
   `CategoryResolverIndex`, for a mention with no literal overlap at all
   ("kicks" for "Women's Running Shoes").

The first two return `confidence="high"` — they matched real, exact text.
`SubstringHandler` returns `"medium"` — plausible, not certain.
`SemanticSearchHandler` can return any tier, computed from the raw
similarity score. Turning a non-`"high"` match into a clarifying question
(rather than silently acting on a guess) is the caller's job (the graph
step) — this module's contract is "the best match found," never
"guaranteed correct."
"""

from typing import Protocol

import chromadb
from chromadb.api.types import EmbeddingFunction

from category_insights.domain.models import Category, CategoryMatch
from category_insights.domain.ports import CategoryResolverIndex

COLLECTION_NAME = "category_resolution_index"
"""Separate from `rag.notes_store.COLLECTION_NAME` — never shared, see `vectorstore.py`."""


class CategoryResolutionHandler(Protocol):
    """One step in the chain: resolve `mention`, or defer to the next handler."""

    def handle(self, mention: str, categories: list[Category]) -> CategoryMatch | None:
        """Return a match, or `None` to let the next handler in the chain try."""
        ...


class ExactNameHandler:
    """Matches `mention` against a category's display name, case-insensitively."""

    def handle(self, mention: str, categories: list[Category]) -> CategoryMatch | None:
        normalized = mention.strip().lower()
        for category in categories:
            if category.name.lower() == normalized:
                return CategoryMatch(
                    category_id=category.category_id,
                    name=category.name,
                    score=1.0,
                    confidence="high",
                )
        return None


class AliasHandler:
    """Matches `mention` against a category's aliases, case-insensitively."""

    def handle(self, mention: str, categories: list[Category]) -> CategoryMatch | None:
        normalized = mention.strip().lower()
        for category in categories:
            if normalized in (alias.lower() for alias in category.aliases):
                return CategoryMatch(
                    category_id=category.category_id,
                    name=category.name,
                    score=1.0,
                    confidence="high",
                )
        return None


class SubstringHandler:
    """Matches when `mention` and a name/alias share one as a substring of the other.

    Among every substring match, picks the tightest one — the candidate
    whose length is closest to `mention`'s, in either direction, is the
    most specific match and least likely to be a coincidence.
    """

    def handle(self, mention: str, categories: list[Category]) -> CategoryMatch | None:
        normalized = mention.strip().lower()
        best_score = 0.0
        best_category: Category | None = None
        for category in categories:
            for candidate in (category.name, *category.aliases):
                candidate_lower = candidate.lower()
                if normalized not in candidate_lower and candidate_lower not in normalized:
                    continue
                shorter = min(len(normalized), len(candidate_lower))
                longer = max(len(normalized), len(candidate_lower))
                score = shorter / longer if longer else 0.0
                if score > best_score:
                    best_score, best_category = score, category

        if best_category is None:
            return None
        return CategoryMatch(
            category_id=best_category.category_id,
            name=best_category.name,
            score=best_score,
            confidence="medium",
        )


class SemanticSearchHandler:
    """Falls back to embedding similarity for a mention with no literal text overlap."""

    def __init__(self, resolver_index: CategoryResolverIndex) -> None:
        self._resolver_index = resolver_index

    def handle(self, mention: str, categories: list[Category]) -> CategoryMatch | None:
        matches = self._resolver_index.search(mention, top_k=1)
        return matches[0] if matches else None


def build_default_handlers(
    resolver_index: CategoryResolverIndex,
) -> list[CategoryResolutionHandler]:
    """The standard 4-handler chain, in resolution order."""
    return [
        ExactNameHandler(),
        AliasHandler(),
        SubstringHandler(),
        SemanticSearchHandler(resolver_index),
    ]


def resolve_category(
    mention: str, categories: list[Category], handlers: list[CategoryResolutionHandler]
) -> CategoryMatch | None:
    """Try each handler in order; return the first match, or `None` if every handler fails.

    With `SemanticSearchHandler` last in the chain, `None` only happens
    when its index is empty (no categories to search at all) — given any
    categories, it always returns *some* candidate, however low its
    confidence. A non-`"high"`-confidence result is a legitimate outcome
    for the caller to turn into a clarifying question, not a failure this
    function retries or discards.
    """
    for handler in handlers:
        match = handler.handle(mention, categories)
        if match is not None:
            return match
    return None


class ChromaCategoryResolverIndex:
    """`CategoryResolverIndex` implementation backed by a Chroma collection.

    Embeds each category as its name plus its aliases joined into one
    document, so a semantic search matches the same words a human would
    use to describe the category. Confidence tiers are computed here, not
    by `SemanticSearchHandler` — this is the layer with the raw
    similarity score, the same split `ChromaNoteRetriever` draws for
    `min_similarity`.
    """

    def __init__(
        self, collection: chromadb.Collection, high_threshold: float, medium_threshold: float
    ) -> None:
        self._collection = collection
        self._high_threshold = high_threshold
        self._medium_threshold = medium_threshold

    def index(self, categories: list[Category]) -> None:
        if not categories:
            return
        self._collection.upsert(
            ids=[str(category.category_id) for category in categories],
            documents=[" ".join([category.name, *category.aliases]) for category in categories],
            metadatas=[
                {"category_id": category.category_id, "name": category.name}
                for category in categories
            ],
        )

    def search(self, mention: str, top_k: int = 3) -> list[CategoryMatch]:
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(query_texts=[mention], n_results=min(top_k, count))
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        matches: list[CategoryMatch] = []
        for metadata, distance in zip(metadatas, distances, strict=True):
            # Cosine space (configured when the collection is created): distance = 1 - similarity.
            score = 1.0 - distance
            if score >= self._high_threshold:
                confidence = "high"
            elif score >= self._medium_threshold:
                confidence = "medium"
            else:
                confidence = "low"
            matches.append(
                CategoryMatch(
                    category_id=int(metadata["category_id"]),
                    name=str(metadata["name"]),
                    score=score,
                    confidence=confidence,
                )
            )
        return matches


def get_or_create_category_index_collection(
    client: chromadb.ClientAPI, embedding_function: EmbeddingFunction
) -> chromadb.Collection:
    """Return the `category_resolution_index` collection, creating it (cosine space) if absent."""
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )
