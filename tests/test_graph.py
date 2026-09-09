"""End-to-end tests for the LangGraph pipeline, built entirely from fakes/temp adapters.

Uses `seeded_repository` (category 1 "Test Category A", alias "alias-a",
10 days of `image_count`/`not_aligned_tax_count` data from 2026-01-01 to
2026-01-10, site 0/US; category 2 "Test Category B" has no metric data)
so date-range math has known, checkable answers.
"""

from datetime import date

import chromadb
from chromadb.api.types import EmbeddingFunction

from category_insights.agent.category_resolution import (
    CategoryResolutionHandler,
    build_default_handlers,
)
from category_insights.agent.graph import answer_question
from category_insights.agent.intent_extraction import ExtractedFields
from category_insights.agent.site_resolution import LearnedSiteAliases
from category_insights.bootstrap import AdapterBundle
from category_insights.db.repository import DuckDbRepository
from category_insights.domain.models import CategoryMatch, Note
from category_insights.domain.ports import CategoryResolverIndex
from category_insights.rag.notes_store import build_notes_index, get_or_create_notes_collection
from category_insights.rag.retriever import ChromaNoteRetriever
from tests.conftest import FakeChatModel


class _UnreachableResolverIndex:
    """Proves the semantic handler was never reached — every other handler matched first."""

    def index(self, categories: object) -> None:
        pass

    def search(self, mention: str, top_k: int = 3) -> list:
        raise AssertionError("Semantic search should not have been reached.")


class _EmptyResolverIndex:
    """A resolver index with nothing in it — every search comes back empty."""

    def index(self, categories: object) -> None:
        pass

    def search(self, mention: str, top_k: int = 3) -> list:
        return []


class _FixedResolverIndex:
    """Always returns the same single match, whatever the query."""

    def __init__(self, match: CategoryMatch) -> None:
        self._match = match

    def index(self, categories: object) -> None:
        pass

    def search(self, mention: str, top_k: int = 3) -> list[CategoryMatch]:
        return [self._match]


def _build_adapters(
    repository: DuckDbRepository,
    chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    embedding_function: EmbeddingFunction,
    notes: list[Note] | None = None,
) -> AdapterBundle:
    notes_collection = get_or_create_notes_collection(chroma_client, embedding_function)
    build_notes_index(notes_collection, notes or [])
    note_retriever = ChromaNoteRetriever(notes_collection, min_similarity=0.0)

    return AdapterBundle(
        repository=repository,
        note_retriever=note_retriever,
        chat_model=chat_model,
        learned_site_aliases=LearnedSiteAliases(repository),
        category_resolver_index=_EmptyResolverIndex(),  # unused: handlers are passed separately
    )


def _handlers(resolver_index: CategoryResolverIndex) -> list[CategoryResolutionHandler]:
    return build_default_handlers(resolver_index)


def test_snapshot_answer_for_an_exact_category_match(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:

    fake_chat_model.set_structured_response(
        ExtractedFields, ExtractedFields(category_mention="Test Category A")
    )
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )

    answer = answer_question(
        "How is Test Category A doing?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "As of 2026-01-10" in answer
    assert "Image count: 89" in answer


def test_history_answer_for_a_recognized_date_phrase(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:

    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(
            category_mention="alias-a",
            metric_keys=["image_count"],
            date_phrase="last 10 days",
        ),
    )
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )

    answer = answer_question(
        "How did image count trend over the last 10 days for Test Category A?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "Image count from 2026-01-01 to 2026-01-10" in answer
    assert "80 -> 89" in answer


def test_comparison_answer_reads_as_an_improvement(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:

    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(
            category_mention="Test Category A",
            metric_keys=["image_count"],
            date_phrase="last 5 days",
            comparison_phrase="last 10 days",
        ),
    )
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )

    answer = answer_question(
        "How do the last 5 days compare to the last 10 days for image count?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "improvement" in answer
    assert "Related analyst notes:" not in answer  # small swing, no "why" asked: no notes pulled


def test_a_large_unasked_for_swing_still_triggers_note_retrieval(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:
    # not_aligned_tax_count falls from 5.0 to 1.85 over the 10 seeded days — a
    # ~46% swing between "today" and the 10-day average, well past the default
    # `category_insights_unexpected_delta_threshold` (10 points), even though
    # `wants_explanation` is never set.
    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(
            category_mention="Test Category A",
            metric_keys=["not_aligned_tax_count"],
            date_phrase="today",
            comparison_phrase="last 10 days",
        ),
    )
    notes = [Note(category_id=1, date=date(2026, 1, 9), body="A migration explains the shift.")]
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function, notes=notes
    )

    answer = answer_question(
        "How does not-aligned tax count today compare to the last 10 days?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "Related analyst notes:" in answer
    assert "A migration explains the shift." in answer


def test_clarifies_when_no_category_is_mentioned(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:

    fake_chat_model.set_structured_response(ExtractedFields, ExtractedFields(category_mention=None))
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )

    answer = answer_question(
        "How are things going?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert answer == "Which category are you asking about?"


def test_clarifies_for_an_unrecognized_category(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:

    fake_chat_model.set_structured_response(
        ExtractedFields, ExtractedFields(category_mention="an entirely unrelated thing")
    )
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )

    answer = answer_question(
        "How is an entirely unrelated thing doing?",
        adapters,
        _handlers(_EmptyResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "don't recognize" in answer


def test_medium_confidence_match_is_offered_as_a_did_you_mean(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:
    fake_chat_model.set_structured_response(
        ExtractedFields, ExtractedFields(category_mention="something shoe-related")
    )
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )
    medium_match = CategoryMatch(
        category_id=1, name="Test Category A", score=0.6, confidence="medium"
    )

    answer = answer_question(
        "How is something shoe-related doing?",
        adapters,
        _handlers(_FixedResolverIndex(medium_match)),
        now=date(2026, 1, 10),
    )

    assert "Did you mean 'Test Category A'?" in answer


def test_low_confidence_match_is_not_offered_as_a_did_you_mean(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:
    # A "low"-confidence semantic hit is the search index's honest floor, not
    # a guess worth naming — this must read as "I don't know," never as a
    # specific (likely wrong) suggestion.
    fake_chat_model.set_structured_response(
        ExtractedFields, ExtractedFields(category_mention="something totally unrelated")
    )
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )
    low_match = CategoryMatch(category_id=2, name="Test Category B", score=0.2, confidence="low")

    answer = answer_question(
        "How is something totally unrelated doing?",
        adapters,
        _handlers(_FixedResolverIndex(low_match)),
        now=date(2026, 1, 10),
    )

    assert "don't recognize" in answer
    assert "Test Category B" not in answer


def test_wants_explanation_appends_matching_notes(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:

    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(category_mention="Test Category A", wants_explanation=True),
    )
    notes = [Note(category_id=1, date=date(2026, 1, 9), body="A migration explains the shift.")]
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function, notes=notes
    )

    answer = answer_question(
        "Why did Test Category A change?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "Related analyst notes:" in answer
    assert "A migration explains the shift." in answer
