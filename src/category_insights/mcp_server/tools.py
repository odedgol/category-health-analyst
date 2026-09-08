"""The 6 MCP tools, each a Command class: `execute(input) -> output`.

Every command's required port (`MetricsRepository`, `NoteRetriever`) is
injected through its constructor — these classes never construct their
own adapters, so a fake repository or retriever is all a test needs.
Tools operate on `category_id: int`, never a free-text category name;
resolving a human's loosely-worded mention to an id is the agent's job
(`agent/category_resolution.py`), not this layer's.
"""

from datetime import date

from pydantic import BaseModel, Field

from category_insights.domain.models import (
    Category,
    CategorySnapshot,
    DateRange,
    MetricPoint,
    NoteChunk,
    PeriodComparison,
)
from category_insights.domain.ports import MetricsRepository, NoteRetriever
from category_insights.metrics import METRICS, MetricKey, TrendDirection


class ListCategoriesInput(BaseModel):
    """No parameters — lists every known category."""


class ListCategoriesOutput(BaseModel):
    """Every category the catalog knows about, with its id, display name, and aliases."""

    categories: list[Category]


class ListCategoriesCommand:
    """Lists every category, so a caller can map a category name to its id."""

    def __init__(self, repository: MetricsRepository) -> None:
        self._repository = repository

    def execute(self, input_model: ListCategoriesInput) -> ListCategoriesOutput:
        return ListCategoriesOutput(categories=self._repository.list_categories())


class MetricInfo(BaseModel):
    """One metric's registry entry: what it means and how to read a change in it."""

    key: str
    display_name: str
    unit: str
    trend_direction: TrendDirection
    description: str


class ListMetricsInput(BaseModel):
    """No parameters — lists every metric in the registry."""


class ListMetricsOutput(BaseModel):
    """Every metric this system tracks, with enough detail to interpret a value or a trend."""

    metrics: list[MetricInfo]


class ListMetricsCommand:
    """Lists every metric, so a caller knows which metric keys are valid and what each means."""

    def execute(self, input_model: ListMetricsInput) -> ListMetricsOutput:
        return ListMetricsOutput(
            metrics=[
                MetricInfo(
                    key=metric.key,
                    display_name=metric.display_name,
                    unit=metric.unit,
                    trend_direction=metric.trend_direction,
                    description=metric.description,
                )
                for metric in METRICS
            ]
        )


class GetMetricHistoryInput(BaseModel):
    """A daily value lookup for one metric, one category, over a date range."""

    category_id: int
    metric_key: MetricKey
    start_date: date
    end_date: date


class GetMetricHistoryOutput(BaseModel):
    """Daily values for the requested metric, ordered by date.

    Empty (not an error) if the category has no data in the requested
    range — an expected outcome, not a failure.
    """

    points: list[MetricPoint]


class GetMetricHistoryCommand:
    """Fetches the daily history of one metric for one category over a date range."""

    def __init__(self, repository: MetricsRepository) -> None:
        self._repository = repository

    def execute(self, input_model: GetMetricHistoryInput) -> GetMetricHistoryOutput:
        points = self._repository.get_metric_series(
            category_id=input_model.category_id,
            metric_key=input_model.metric_key,
            start=input_model.start_date,
            end=input_model.end_date,
        )
        return GetMetricHistoryOutput(points=points)


class CompareMetricPeriodsInput(BaseModel):
    """Compares one metric's average value between an earlier and a later period.

    `period_a_*` is the earlier/baseline period, `period_b_*` is the
    later/comparison period — e.g. for "this month vs last month",
    `period_a` is last month and `period_b` is this month.
    """

    category_id: int
    metric_key: MetricKey
    period_a_start: date
    period_a_end: date
    period_b_start: date
    period_b_end: date


class CompareMetricPeriodsOutput(BaseModel):
    """The comparison result: both period averages, the delta, and whether it's an improvement."""

    comparison: PeriodComparison


class CompareMetricPeriodsCommand:
    """Compares one metric's average value across two periods for one category.

    Raises:
        MetricDataUnavailableError: if either period has no data — the
            caller (the agent) is expected to catch this specific
            exception and answer honestly rather than guess.
    """

    def __init__(self, repository: MetricsRepository) -> None:
        self._repository = repository

    def execute(self, input_model: CompareMetricPeriodsInput) -> CompareMetricPeriodsOutput:
        comparison = self._repository.compare_periods(
            category_id=input_model.category_id,
            metric_key=input_model.metric_key,
            period_a=DateRange(start=input_model.period_a_start, end=input_model.period_a_end),
            period_b=DateRange(start=input_model.period_b_start, end=input_model.period_b_end),
        )
        return CompareMetricPeriodsOutput(comparison=comparison)


class GetCategorySnapshotInput(BaseModel):
    """A single point-in-time read of every metric for one category.

    Defaults to the most recent available date when `as_of_date` is omitted.
    """

    category_id: int
    as_of_date: date | None = None


class GetCategorySnapshotOutput(BaseModel):
    """Every metric for the category on the resolved date, or `None` if there's no data at all."""

    snapshot: CategorySnapshot | None


class GetCategorySnapshotCommand:
    """Fetches every metric for one category on one day (or the latest day, by default)."""

    def __init__(self, repository: MetricsRepository) -> None:
        self._repository = repository

    def execute(self, input_model: GetCategorySnapshotInput) -> GetCategorySnapshotOutput:
        snapshot = self._repository.get_latest_snapshot(
            category_id=input_model.category_id, as_of_date=input_model.as_of_date
        )
        return GetCategorySnapshotOutput(snapshot=snapshot)


class SearchCategoryNotesInput(BaseModel):
    """A retrieval-only search over the category-notes corpus for one category.

    `query` should describe what needs explaining (e.g. the metric and
    rough date range), not just repeat "why did this change" — the
    retriever ranks by similarity to this text.
    """

    category_id: int
    query: str
    top_k: int = Field(default=3, ge=1, le=10)


class SearchCategoryNotesOutput(BaseModel):
    """Matching note chunks with their date and similarity score, ranked highest first.

    Empty (not a guess) when nothing relevant was found for this
    category — this tool never generates an explanation itself, it only
    retrieves; composing the final answer is the agent's job.
    """

    notes: list[NoteChunk]


class SearchCategoryNotesCommand:
    """Retrieves analyst notes for one category that are similar to `query`."""

    def __init__(self, note_retriever: NoteRetriever) -> None:
        self._note_retriever = note_retriever

    def execute(self, input_model: SearchCategoryNotesInput) -> SearchCategoryNotesOutput:
        notes = self._note_retriever.retrieve_category_notes(
            category_id=input_model.category_id,
            query=input_model.query,
            top_k=input_model.top_k,
        )
        return SearchCategoryNotesOutput(notes=notes)
