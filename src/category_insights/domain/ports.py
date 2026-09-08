"""Port protocols: the contracts every adapter and the agent depend on.

Each `Protocol` here is structural — an adapter satisfies it by having the
right methods, not by inheriting from anything, so a fake used in tests
needs no shared base class either. This is what lets `db/`, `rag/`, and
`agent/category_resolution.py` be swapped for a different implementation
(a real ClickHouse client, pgvector, a different LLM provider) without
changing any code that depends on the protocol.
"""

from datetime import date
from typing import Any, Protocol, TypeVar, runtime_checkable

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from category_insights.domain.models import (
    Category,
    CategoryMatch,
    CategorySnapshot,
    DateRange,
    MetricPoint,
    NoteChunk,
    PeriodComparison,
)

T = TypeVar("T")


class MetricDataUnavailableError(Exception):
    """Raised when a requested metric comparison has no data in one or both periods.

    This is an expected, answerable outcome ("I don't have data for that
    date range"), not a bug — callers at a system boundary (MCP tools, the
    agent) are expected to catch this specific exception and turn it into
    an honest user-facing response rather than let it propagate as a raw
    error or, worse, silently compute a comparison against missing data.
    """


@runtime_checkable
class MetricsRepository(Protocol):
    """Read access to category master data and their daily metric snapshots.

    Implemented against DuckDB today (`db/repository.py::DuckDbRepository`)
    as a stand-in for a real ClickHouse cluster — every method here is the
    one surface that would need a new adapter, not a rewrite, to point at
    a real analytics store.
    """

    def list_categories(self) -> list[Category]:
        """Return every known category with its id, display name, and aliases.

        Categories are site-independent — the same category exists across
        every site, only its daily metrics differ by site.
        """
        ...

    def get_metric_series(
        self, category_id: int, site_id: int, metric_key: str, start: date, end: date
    ) -> list[MetricPoint]:
        """Return the daily values of one metric for one category/site, inclusive of both dates."""
        ...

    def compare_periods(
        self,
        category_id: int,
        site_id: int,
        metric_key: str,
        period_a: DateRange,
        period_b: DateRange,
    ) -> PeriodComparison:
        """Compare a metric's average value across two periods, for one category/site.

        `period_a` is treated as the earlier/baseline period.

        Raises:
            MetricDataUnavailableError: if either period has no data points
                for this category/site/metric.
        """
        ...

    def get_latest_snapshot(
        self, category_id: int, site_id: int, as_of_date: date | None = None
    ) -> CategorySnapshot | None:
        """Return every metric for a category/site on `as_of_date` (or the latest date if omitted).

        Returns `None` if there's no snapshot on or before that date,
        rather than raising — a missing snapshot is an expected,
        answerable outcome ("I don't have data for that"), not an error.
        """
        ...


@runtime_checkable
class NoteRetriever(Protocol):
    """Retrieval over the category-notes corpus, grounding "why" answers.

    Implementations must filter by `category_id` before ranking by
    similarity, and must return an empty list — never a low-confidence
    guess — when nothing clears the minimum similarity threshold.
    """

    def retrieve_category_notes(
        self, category_id: int, query: str, top_k: int = 3
    ) -> list[NoteChunk]:
        """Return up to `top_k` note chunks for `category_id` relevant to `query`."""
        ...


@runtime_checkable
class CategoryResolverIndex(Protocol):
    """Semantic fallback for matching a loosely-worded category mention.

    A stand-in for what would, in a real system, likely be a proper vector
    database (pgvector, Pinecone) or a dedicated category-search
    microservice. The agent's Chain of Responsibility only calls this as
    its last handler, after exact/alias/substring matching has already
    failed — so this interface only needs to handle the fuzzy case.
    """

    def index(self, categories: list[Category]) -> None:
        """(Re)build the index from the current set of categories."""
        ...

    def search(self, mention: str, top_k: int = 3) -> list[CategoryMatch]:
        """Return up to `top_k` candidate categories ranked by similarity to `mention`."""
        ...


@runtime_checkable
class SiteAliasStore(Protocol):
    """Persists site aliases learned from an LLM classification, across restarts.

    `agent.site_resolution.resolve_site_with_learning` is the only
    consumer: it checks `sites.match_known_site` first, then a learned
    alias, and only calls the LLM — then writes through here — when
    neither matches. Kept as its own small port rather than folded into
    `MetricsRepository`, since it's a different concern (site reference
    data, not category metrics) with a different lifecycle (grows over
    time from LLM answers, not seeded from a fixture).
    """

    def list_learned_aliases(self) -> dict[str, int]:
        """Return every learned alias -> site_id mapping, for loading into memory at startup."""
        ...

    def save_learned_alias(self, alias: str, site_id: int) -> None:
        """Persist one alias -> site_id mapping. Upsert: safe to call again for the same alias."""
        ...


class ChatModel(Protocol):
    """The minimal surface of an LLM the agent depends on.

    Deliberately narrower than `langchain_core.BaseChatModel`'s full
    surface — any real LangChain chat model already satisfies this
    structurally, so `agent/llm.py::ChatModelProvider` can return one
    directly with no wrapper class.
    """

    def invoke(self, input: list[BaseMessage]) -> BaseMessage:
        """Send messages to the model and return its reply."""
        ...

    def with_structured_output(self, schema: type[T]) -> "Runnable[Any, T]":
        """Return a runnable that parses the model's reply into `schema`."""
        ...
