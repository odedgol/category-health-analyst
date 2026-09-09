"""End-to-end tests for the LangGraph pipeline, built entirely from fakes/temp adapters.

Uses `seeded_repository` (category 1 "Test Category A", alias "alias-a",
10 days of `image_count`/`not_aligned_tax_count` data from 2026-01-01 to
2026-01-10, site 0/US; category 2 "Test Category B" has no metric data)
so date-range math has known, checkable answers.
"""

from datetime import date

import chromadb
import pytest
from chromadb.api.types import EmbeddingFunction

from category_insights.agent import graph as graph_module
from category_insights.agent.category_resolution import (
    CategoryResolutionHandler,
    build_default_handlers,
)
from category_insights.agent.graph import _example_categories_hint, answer_question
from category_insights.agent.intent_extraction import ExtractedFields
from category_insights.agent.site_resolution import LearnedSiteAliases
from category_insights.bootstrap import AdapterBundle
from category_insights.db.repository import DuckDbRepository
from category_insights.domain.models import Category, CategoryMatch, Note
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

    result = answer_question(
        "How is Test Category A doing?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "As of 2026-01-10" in result.text
    assert "Image count: 89" in result.text


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

    result = answer_question(
        "How did image count trend over the last 10 days for Test Category A?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "Image count from 2026-01-01 to 2026-01-10" in result.text
    assert "80 -> 89" in result.text


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

    result = answer_question(
        "How do the last 5 days compare to the last 10 days for image count?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "improvement" in result.text
    assert (
        "Related analyst notes:" not in result.text
    )  # small swing, no "why" asked: no notes pulled


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

    result = answer_question(
        "How does not-aligned tax count today compare to the last 10 days?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "Related analyst notes:" in result.text
    assert "A migration explains the shift." in result.text


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

    result = answer_question(
        "How are things going?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    # seeded_repository has exactly "Test Category A" and "Test Category B" —
    # both fit under _EXAMPLE_CATEGORY_COUNT, so both are named as examples.
    assert result.text == (
        "Which category are you asking about? For example: Test Category A, Test Category B."
    )


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

    result = answer_question(
        "How is an entirely unrelated thing doing?",
        adapters,
        _handlers(_EmptyResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "don't recognize" in result.text


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

    result = answer_question(
        "How is something shoe-related doing?",
        adapters,
        _handlers(_FixedResolverIndex(medium_match)),
        now=date(2026, 1, 10),
    )

    assert "Did you mean 'Test Category A'?" in result.text


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

    result = answer_question(
        "How is something totally unrelated doing?",
        adapters,
        _handlers(_FixedResolverIndex(low_match)),
        now=date(2026, 1, 10),
    )

    assert "don't recognize" in result.text
    # Not offered as a specific suggestion — "Test Category B" may still
    # appear as a generic catalog example (both seeded categories do), but
    # never framed as "did you mean the low-confidence guess?".
    assert "Did you mean" not in result.text


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

    result = answer_question(
        "Why did Test Category A change?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert "Related analyst notes:" in result.text
    assert "A migration explains the shift." in result.text


def test_history_is_threaded_from_answer_question_into_extract_intent(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wiring test for the "clarification never gets resolved" bug.

    `FakeChatModel` returns the same canned response regardless of prompt
    content, so it can't prove the *model* uses history correctly — only a
    real model call can. What this proves is the plumbing: the `history`
    `answer_question()` is given actually reaches `extract_intent`, by
    intercepting the call and recording what it received.
    """
    captured_history = []

    real_extract_intent = graph_module.extract_intent

    def _spy_extract_intent(question, chat_model, now, history=None):
        captured_history.append(history)
        return real_extract_intent(question, chat_model, now, history=history)

    monkeypatch.setattr(graph_module, "extract_intent", _spy_extract_intent)

    fake_chat_model.set_structured_response(
        ExtractedFields, ExtractedFields(category_mention="Test Category A")
    )
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )
    history = [
        ("user", "how are things going"),
        ("assistant", "Which category are you asking about?"),
    ]

    answer_question(
        "Test Category A",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
        history=history,
    )

    assert captured_history == [history]


def test_snapshot_result_carries_the_structured_snapshot(
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

    result = answer_question(
        "How is Test Category A doing?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert result.metric_series == {}
    assert result.comparisons == []
    assert result.snapshot is not None
    assert result.snapshot.metrics["image_count"] == 89.0


def test_history_result_carries_the_structured_metric_series(
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
            date_phrase="last 10 days",
        ),
    )
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )

    result = answer_question(
        "How did image count trend over the last 10 days?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert result.snapshot is None
    assert result.comparisons == []
    assert set(result.metric_series) == {"image_count"}
    assert [point.value for point in result.metric_series["image_count"]] == pytest.approx(
        [80.0 + i for i in range(10)]
    )


def test_comparison_result_carries_the_structured_comparisons(
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

    result = answer_question(
        "How do the last 5 days compare to the last 10 days for image count?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert result.snapshot is None
    assert result.metric_series == {}
    assert len(result.comparisons) == 1
    assert result.comparisons[0].metric_key == "image_count"
    assert result.comparisons[0].improved is True


def test_clarification_result_carries_no_structured_data(
    seeded_repository: DuckDbRepository,
    fake_chat_model: FakeChatModel,
    chroma_client: chromadb.ClientAPI,
    fake_embedding_function: EmbeddingFunction,
) -> None:
    fake_chat_model.set_structured_response(ExtractedFields, ExtractedFields(category_mention=None))
    adapters = _build_adapters(
        seeded_repository, fake_chat_model, chroma_client, fake_embedding_function
    )

    result = answer_question(
        "How are things going?",
        adapters,
        _handlers(_UnreachableResolverIndex()),
        now=date(2026, 1, 10),
    )

    assert result.metric_series == {}
    assert result.comparisons == []
    assert result.snapshot is None


def test_example_categories_hint_lists_up_to_three_names() -> None:
    categories = [Category(category_id=i, name=f"Category {i}", aliases=[]) for i in range(1, 6)]

    hint = _example_categories_hint(categories)

    assert hint == " For example: Category 1, Category 2, Category 3."


def test_example_categories_hint_is_empty_for_an_empty_catalog() -> None:
    assert _example_categories_hint([]) == ""
