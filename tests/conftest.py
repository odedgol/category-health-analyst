"""Shared pytest fixtures.

Fixtures are added here as the sprint that needs them lands, rather than
stubbed out ahead of time — a fixture with no current user is dead weight
until something actually depends on it.
"""

import hashlib
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import chromadb
import duckdb
import pytest
from chromadb.api.types import Documents, Embeddings
from chromadb.api.types import EmbeddingFunction as ChromaEmbeddingFunction

from category_insights.db.connection import bootstrap_schema
from category_insights.db.repository import DuckDbRepository
from category_insights.domain.models import Category, MetricPoint


@pytest.fixture
def fixed_now() -> date:
    """A fixed reference date for deterministic date-range parsing tests.

    Never call `date.today()` inside parsing logic — always resolve
    relative phrases ("last week") against an explicit `now` so tests
    don't depend on when they happen to run.
    """
    return date(2026, 6, 15)


@pytest.fixture
def temp_duckdb(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """A fresh, schema-bootstrapped DuckDB file under pytest's tmp_path."""
    connection = duckdb.connect(str(tmp_path / "test_warehouse.duckdb"))
    bootstrap_schema(connection)
    try:
        yield connection
    finally:
        connection.close()


SEEDED_SITE_ID = 0  # US, per sites.DEFAULT_SITE_ID


@pytest.fixture
def seeded_repository(temp_duckdb: duckdb.DuckDBPyConnection) -> DuckDbRepository:
    """A `DuckDbRepository` pre-loaded with two categories and 10 days of hand-crafted metrics.

    Both at site 0 (US). Category 1's `image_count` rises linearly from
    80 to 89 (higher-is-better improvement) and `not_aligned_tax_count`
    falls from 5 to 1.5 (lower-is-better improvement) — fixed, known
    values so `compare_periods` and `get_metric_series` assertions don't
    depend on randomness.
    """
    repository = DuckDbRepository(temp_duckdb)
    repository.insert_categories(
        [
            Category(category_id=1, name="Test Category A", aliases=["alias-a"]),
            Category(category_id=2, name="Test Category B", aliases=[]),
        ]
    )

    points: list[MetricPoint] = []
    for day_offset in range(10):
        day = date(2026, 1, 1 + day_offset)
        points.append(
            MetricPoint(
                category_id=1,
                site_id=SEEDED_SITE_ID,
                metric_key="image_count",
                date=day,
                value=80.0 + day_offset,
            )
        )
        points.append(
            MetricPoint(
                category_id=1,
                site_id=SEEDED_SITE_ID,
                metric_key="not_aligned_tax_count",
                date=day,
                value=5.0 - 0.35 * day_offset,
            )
        )
    repository.insert_metric_points(points)
    return repository


class FakeEmbeddingFunction(ChromaEmbeddingFunction[Documents]):
    """Deterministic, offline bag-of-words embedding — no network, no ML model.

    Used by any test that needs a Chroma collection but must not depend on
    a live OpenAI call or a downloaded model. Identical text always
    produces an identical vector; texts sharing more words score more
    similar under cosine distance — good enough to test retrieval logic
    (filtering, thresholds, ordering), which doesn't depend on genuine
    semantic quality. Subclasses chromadb's `EmbeddingFunction` (rather
    than just duck-typing it) to inherit its default `embed_query`.
    """

    def __init__(self) -> None:
        pass

    _DIMENSIONS = 64

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002 (name required by chromadb's protocol)
        return [self._embed(text) for text in input]

    def name(self) -> str:
        return "fake-bag-of-words"

    def get_config(self) -> dict[str, object]:
        return {}

    @staticmethod
    def build_from_config(config: dict[str, object]) -> "FakeEmbeddingFunction":
        return FakeEmbeddingFunction()

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._DIMENSIONS
        for word in text.lower().split():
            index = int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16)
            vector[index % self._DIMENSIONS] += 1.0
        norm = sum(component * component for component in vector) ** 0.5
        if norm == 0:
            return vector
        return [component / norm for component in vector]


@pytest.fixture
def fake_embedding_function() -> FakeEmbeddingFunction:
    return FakeEmbeddingFunction()


@pytest.fixture
def chroma_client() -> chromadb.ClientAPI:
    """An isolated, in-memory Chroma client — fresh per test, nothing persisted to disk.

    `chromadb.EphemeralClient()` calls with default settings share an
    internal system cache within one process, so without an explicit
    `reset()` a collection created in one test would still be visible
    (and non-empty) in the next. `allow_reset=True` + `reset()` guarantees
    each test actually starts from a clean slate.
    """
    client = chromadb.EphemeralClient(settings=chromadb.config.Settings(allow_reset=True))
    client.reset()
    return client


class _FakeStructuredRunnable:
    def __init__(self, response: object) -> None:
        self._response = response

    def invoke(self, messages: object) -> object:
        return self._response


class FakeChatModel:
    """Test double satisfying `domain.ports.ChatModel` — no network call, ever.

    Configure a canned response per output schema via
    `set_structured_response`, and a canned plain-text reply via
    `set_invoke_response`. Calling `.with_structured_output()` for a
    schema with no configured response raises `AssertionError` — this is
    what lets a test prove an LLM call for a given schema was (or wasn't)
    made, e.g. that a fast-path-recognized date phrase never reaches the
    LLM date-parsing fallback.
    """

    def __init__(self) -> None:
        self._structured_responses: dict[type, object] = {}
        self._invoke_response: object | None = None
        self.structured_call_counts: dict[type, int] = {}
        self.invoke_call_count = 0

    def set_structured_response(self, schema: type, response: object) -> None:
        self._structured_responses[schema] = response

    def set_invoke_response(self, response: object) -> None:
        self._invoke_response = response

    def invoke(self, messages: object) -> object:
        self.invoke_call_count += 1
        if self._invoke_response is None:
            raise AssertionError("FakeChatModel.invoke() called with no response configured.")
        return self._invoke_response

    def with_structured_output(self, schema: type) -> _FakeStructuredRunnable:
        if schema not in self._structured_responses:
            raise AssertionError(
                f"FakeChatModel has no configured structured response for {schema} "
                "— unexpected LLM call."
            )
        self.structured_call_counts[schema] = self.structured_call_counts.get(schema, 0) + 1
        return _FakeStructuredRunnable(self._structured_responses[schema])


@pytest.fixture
def fake_chat_model() -> FakeChatModel:
    return FakeChatModel()
