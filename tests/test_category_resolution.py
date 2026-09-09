"""Tests for the category-resolution Chain of Responsibility.

Handler-chain tests use a fake `CategoryResolverIndex` (no Chroma
involved) so they run instantly and only exercise ordering/fallthrough.
`ChromaCategoryResolverIndex` itself is tested separately against a real
in-memory Chroma collection with `FakeEmbeddingFunction`, mirroring
`test_rag_retriever.py`.
"""

import chromadb
from chromadb.api.types import EmbeddingFunction

from category_insights.agent.category_resolution import (
    AliasHandler,
    ChromaCategoryResolverIndex,
    ExactNameHandler,
    SemanticSearchHandler,
    SubstringHandler,
    build_default_handlers,
    get_or_create_category_index_collection,
    resolve_category,
)
from category_insights.domain.models import Category, CategoryMatch

CATEGORIES = [
    Category(category_id=1, name="Women's Running Shoes", aliases=["sneakers", "running shoes"]),
    Category(category_id=2, name="Laptop Chargers", aliases=["charger cables"]),
]


class _FakeResolverIndex:
    def __init__(self, matches: list[CategoryMatch]) -> None:
        self._matches = matches

    def index(self, categories: list[Category]) -> None:
        pass

    def search(self, mention: str, top_k: int = 3) -> list[CategoryMatch]:
        return self._matches[:top_k]


def test_exact_name_handler_matches_case_insensitively() -> None:
    match = ExactNameHandler().handle("women's running shoes", CATEGORIES)

    assert match is not None
    assert (match.category_id, match.confidence) == (1, "high")


def test_alias_handler_matches() -> None:
    match = AliasHandler().handle("sneakers", CATEGORIES)

    assert match is not None
    assert (match.category_id, match.confidence) == (1, "high")


def test_exact_name_handler_returns_none_for_no_match() -> None:
    assert ExactNameHandler().handle("shoes", CATEGORIES) is None


def test_substring_handler_picks_the_tightest_match() -> None:
    # "shoes" is a substring of both "Women's Running Shoes" (name) and
    # "running shoes" (alias) — the alias is the tighter match.
    match = SubstringHandler().handle("shoes", CATEGORIES)

    assert match is not None
    assert match.category_id == 1
    assert match.confidence == "medium"


def test_substring_handler_returns_none_with_no_overlap() -> None:
    assert SubstringHandler().handle("vinyl records", CATEGORIES) is None


def test_semantic_search_handler_delegates_to_the_index() -> None:
    expected = CategoryMatch(category_id=2, name="Laptop Chargers", score=0.4, confidence="low")
    handler = SemanticSearchHandler(_FakeResolverIndex([expected]))

    assert handler.handle("power brick", CATEGORIES) == expected


def test_semantic_search_handler_returns_none_for_empty_index() -> None:
    handler = SemanticSearchHandler(_FakeResolverIndex([]))

    assert handler.handle("anything", CATEGORIES) is None


def test_resolve_category_prefers_earlier_handlers_in_the_chain() -> None:
    # An exact match exists, so the semantic fallback must never be reached.
    semantic_match = CategoryMatch(
        category_id=2, name="Laptop Chargers", score=0.9, confidence="high"
    )
    handlers = build_default_handlers(_FakeResolverIndex([semantic_match]))

    match = resolve_category("Women's Running Shoes", CATEGORIES, handlers)

    assert match is not None
    assert match.category_id == 1


def test_resolve_category_falls_through_to_the_semantic_handler() -> None:
    semantic_match = CategoryMatch(
        category_id=1, name="Women's Running Shoes", score=0.62, confidence="medium"
    )
    handlers = build_default_handlers(_FakeResolverIndex([semantic_match]))

    match = resolve_category("kicks", CATEGORIES, handlers)

    assert match == semantic_match


def test_resolve_category_returns_none_when_every_handler_fails() -> None:
    handlers = build_default_handlers(_FakeResolverIndex([]))

    assert resolve_category("kicks", CATEGORIES, handlers) is None


def _build_index(
    chroma_client: chromadb.ClientAPI,
    embedding_function: EmbeddingFunction,
    categories: list[Category],
    high_threshold: float = 0.75,
    medium_threshold: float = 0.5,
) -> ChromaCategoryResolverIndex:
    collection = get_or_create_category_index_collection(chroma_client, embedding_function)
    index = ChromaCategoryResolverIndex(collection, high_threshold, medium_threshold)
    index.index(categories)
    return index


def test_chroma_index_search_returns_empty_for_an_empty_collection(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    index = _build_index(chroma_client, fake_embedding_function, categories=[])

    assert index.search("anything") == []


def test_chroma_index_assigns_high_confidence_to_a_close_match(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    index = _build_index(chroma_client, fake_embedding_function, CATEGORIES, high_threshold=0.0)

    matches = index.search("Women's Running Shoes", top_k=1)

    assert matches
    assert matches[0].category_id == 1
    assert matches[0].confidence == "high"


def test_chroma_index_assigns_low_confidence_below_the_medium_threshold(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    index = _build_index(
        chroma_client,
        fake_embedding_function,
        CATEGORIES,
        high_threshold=1.1,
        medium_threshold=1.05,
    )

    matches = index.search("Women's Running Shoes", top_k=1)

    assert matches
    assert matches[0].confidence == "low"


def test_chroma_index_search_respects_top_k(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    index = _build_index(chroma_client, fake_embedding_function, CATEGORIES)

    assert len(index.search("shoes", top_k=1)) == 1
