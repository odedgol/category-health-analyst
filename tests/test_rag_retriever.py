"""Tests for `ChromaNoteRetriever` against an in-memory Chroma collection.

Uses `FakeEmbeddingFunction` (conftest.py) — deterministic and offline —
so these tests never make a network call and never depend on a live
OpenAI key, matching the "no live LLM/embedding calls in tests" rule.
"""

from datetime import date

import chromadb
import pytest
from chromadb.api.types import EmbeddingFunction

from category_insights.domain.models import Note
from category_insights.rag.notes_store import build_notes_index, get_or_create_notes_collection
from category_insights.rag.retriever import ChromaNoteRetriever


def _build_collection(
    client: chromadb.ClientAPI, embedding_function: EmbeddingFunction, notes: list[Note]
) -> chromadb.Collection:
    collection = get_or_create_notes_collection(client, embedding_function)
    build_notes_index(collection, notes)
    return collection


def test_retrieve_filters_by_category_id_before_similarity(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    notes = [
        Note(category_id=1, date=date(2026, 1, 1), body="banana apple orange"),
        # More similar to the query than category 1's note, but must never leak into its results.
        Note(category_id=2, date=date(2026, 1, 2), body="banana apple orange fantastic wonderful"),
    ]
    collection = _build_collection(chroma_client, fake_embedding_function, notes)
    retriever = ChromaNoteRetriever(collection, min_similarity=0.0)

    results = retriever.retrieve_category_notes(
        category_id=1, query="banana apple orange fantastic", top_k=5
    )

    assert results
    assert all(chunk.category_id == 1 for chunk in results)


def test_results_are_sorted_by_score_descending(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    notes = [
        Note(category_id=1, date=date(2026, 1, 1), body="wireless bluetooth headphones"),
        Note(category_id=1, date=date(2026, 1, 2), body="wireless bluetooth"),
        Note(category_id=1, date=date(2026, 1, 3), body="cast iron skillet"),
    ]
    collection = _build_collection(chroma_client, fake_embedding_function, notes)
    retriever = ChromaNoteRetriever(collection, min_similarity=0.0)

    results = retriever.retrieve_category_notes(
        category_id=1, query="wireless bluetooth headphones", top_k=5
    )

    scores = [chunk.score for chunk in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0].body == "wireless bluetooth headphones"


def test_empty_list_when_nothing_clears_the_similarity_threshold(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    notes = [Note(category_id=1, date=date(2026, 1, 1), body="cast iron skillet")]
    collection = _build_collection(chroma_client, fake_embedding_function, notes)
    retriever = ChromaNoteRetriever(collection, min_similarity=0.99)

    results = retriever.retrieve_category_notes(
        category_id=1, query="wireless bluetooth headphones", top_k=5
    )

    assert results == []


def test_note_chunk_carries_the_source_date(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    notes = [Note(category_id=1, date=date(2026, 3, 14), body="taxonomy migration explanation")]
    collection = _build_collection(chroma_client, fake_embedding_function, notes)
    retriever = ChromaNoteRetriever(collection, min_similarity=0.0)

    results = retriever.retrieve_category_notes(category_id=1, query="taxonomy migration", top_k=5)

    assert results[0].date == date(2026, 3, 14)


def test_top_k_limits_the_number_of_results(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    notes = [
        Note(category_id=1, date=date(2026, 1, 1 + i), body=f"note number {i} about widgets")
        for i in range(5)
    ]
    collection = _build_collection(chroma_client, fake_embedding_function, notes)
    retriever = ChromaNoteRetriever(collection, min_similarity=0.0)

    results = retriever.retrieve_category_notes(category_id=1, query="widgets", top_k=2)

    assert len(results) == 2


@pytest.mark.parametrize("category_id", [1, 2])
def test_retrieve_returns_empty_for_a_category_with_no_notes_at_all(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction, category_id: int
) -> None:
    collection = _build_collection(chroma_client, fake_embedding_function, notes=[])
    retriever = ChromaNoteRetriever(collection, min_similarity=0.0)

    assert (
        retriever.retrieve_category_notes(category_id=category_id, query="anything", top_k=5) == []
    )
