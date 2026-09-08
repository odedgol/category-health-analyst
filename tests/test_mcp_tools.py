"""Tests for the 6 MCP tool Command classes, called directly — no MCP transport involved."""

from datetime import date

import chromadb
import pytest
from chromadb.api.types import EmbeddingFunction
from pydantic import ValidationError

from category_insights.db.repository import DuckDbRepository
from category_insights.domain.models import Note
from category_insights.domain.ports import MetricDataUnavailableError
from category_insights.mcp_server.tools import (
    CompareMetricPeriodsCommand,
    CompareMetricPeriodsInput,
    GetCategorySnapshotCommand,
    GetCategorySnapshotInput,
    GetMetricHistoryCommand,
    GetMetricHistoryInput,
    ListCategoriesCommand,
    ListCategoriesInput,
    ListMetricsCommand,
    ListMetricsInput,
    SearchCategoryNotesCommand,
    SearchCategoryNotesInput,
)
from category_insights.rag.notes_store import build_notes_index, get_or_create_notes_collection
from category_insights.rag.retriever import ChromaNoteRetriever


def test_list_categories_returns_every_seeded_category(seeded_repository: DuckDbRepository) -> None:
    output = ListCategoriesCommand(seeded_repository).execute(ListCategoriesInput())
    assert [c.category_id for c in output.categories] == [1, 2]


def test_list_metrics_returns_all_nine_metrics() -> None:
    output = ListMetricsCommand().execute(ListMetricsInput())
    assert len(output.metrics) == 9
    assert {m.key for m in output.metrics} == {
        "product_count",
        "image_coverage_pct",
        "multi_image_pct",
        "taxonomy_alignment_pct",
        "attribute_completeness_pct",
        "price_anomaly_rate_pct",
        "duplicate_rate_pct",
        "orphan_rate_pct",
        "freshness_pct",
    }


def test_get_metric_history_happy_path(seeded_repository: DuckDbRepository) -> None:
    command = GetMetricHistoryCommand(seeded_repository)
    output = command.execute(
        GetMetricHistoryInput(
            category_id=1,
            metric_key="image_coverage_pct",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
        )
    )
    assert [p.value for p in output.points] == pytest.approx([80.0, 81.0, 82.0])


def test_get_metric_history_rejects_unknown_metric_key_at_construction() -> None:
    with pytest.raises(ValidationError):
        GetMetricHistoryInput(
            category_id=1,
            metric_key="not_a_real_metric",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
        )


def test_get_metric_history_returns_empty_for_unknown_category(
    seeded_repository: DuckDbRepository,
) -> None:
    command = GetMetricHistoryCommand(seeded_repository)
    output = command.execute(
        GetMetricHistoryInput(
            category_id=999,
            metric_key="image_coverage_pct",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
        )
    )
    assert output.points == []


def test_compare_metric_periods_happy_path(seeded_repository: DuckDbRepository) -> None:
    command = CompareMetricPeriodsCommand(seeded_repository)
    output = command.execute(
        CompareMetricPeriodsInput(
            category_id=1,
            metric_key="image_coverage_pct",
            period_a_start=date(2026, 1, 1),
            period_a_end=date(2026, 1, 5),
            period_b_start=date(2026, 1, 6),
            period_b_end=date(2026, 1, 10),
        )
    )
    assert output.comparison.improved is True
    assert output.comparison.value_a == pytest.approx(82.0)
    assert output.comparison.value_b == pytest.approx(87.0)


def test_compare_metric_periods_raises_when_no_data(seeded_repository: DuckDbRepository) -> None:
    command = CompareMetricPeriodsCommand(seeded_repository)
    with pytest.raises(MetricDataUnavailableError):
        command.execute(
            CompareMetricPeriodsInput(
                category_id=2,
                metric_key="image_coverage_pct",
                period_a_start=date(2026, 1, 1),
                period_a_end=date(2026, 1, 5),
                period_b_start=date(2026, 1, 6),
                period_b_end=date(2026, 1, 10),
            )
        )


def test_compare_metric_periods_rejects_unknown_metric_key_at_construction() -> None:
    with pytest.raises(ValidationError):
        CompareMetricPeriodsInput(
            category_id=1,
            metric_key="not_a_real_metric",
            period_a_start=date(2026, 1, 1),
            period_a_end=date(2026, 1, 5),
            period_b_start=date(2026, 1, 6),
            period_b_end=date(2026, 1, 10),
        )


def test_get_category_snapshot_happy_path(seeded_repository: DuckDbRepository) -> None:
    command = GetCategorySnapshotCommand(seeded_repository)
    output = command.execute(GetCategorySnapshotInput(category_id=1, as_of_date=date(2026, 1, 4)))
    assert output.snapshot is not None
    assert output.snapshot.metrics["image_coverage_pct"] == pytest.approx(83.0)


def test_get_category_snapshot_returns_none_for_unknown_category(
    seeded_repository: DuckDbRepository,
) -> None:
    command = GetCategorySnapshotCommand(seeded_repository)
    output = command.execute(GetCategorySnapshotInput(category_id=999))
    assert output.snapshot is None


def _build_note_retriever(
    chroma_client: chromadb.ClientAPI, embedding_function: EmbeddingFunction, notes: list[Note]
) -> ChromaNoteRetriever:
    collection = get_or_create_notes_collection(chroma_client, embedding_function)
    build_notes_index(collection, notes)
    return ChromaNoteRetriever(collection, min_similarity=0.0)


def test_search_category_notes_happy_path(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    notes = [Note(category_id=1, date=date(2026, 3, 14), body="taxonomy migration explanation")]
    retriever = _build_note_retriever(chroma_client, fake_embedding_function, notes)
    command = SearchCategoryNotesCommand(retriever)

    output = command.execute(
        SearchCategoryNotesInput(category_id=1, query="taxonomy migration", top_k=3)
    )

    assert len(output.notes) == 1
    assert output.notes[0].date == date(2026, 3, 14)


def test_search_category_notes_returns_empty_for_category_with_no_notes(
    chroma_client: chromadb.ClientAPI, fake_embedding_function: EmbeddingFunction
) -> None:
    retriever = _build_note_retriever(chroma_client, fake_embedding_function, notes=[])
    command = SearchCategoryNotesCommand(retriever)

    output = command.execute(SearchCategoryNotesInput(category_id=1, query="anything", top_k=3))

    assert output.notes == []
