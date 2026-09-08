"""Domain models: the Pydantic shapes that cross every boundary in the system.

These are the only objects that flow between layers — a DB row becomes a
`MetricPoint`, an MCP tool call returns a `PeriodComparison`, the agent's
extracted intent is a `QueryIntent`. No layer passes a raw dict or tuple
across a boundary.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Category(BaseModel):
    """A product category as identified in the catalog.

    `category_id` is the stable, authoritative identifier used everywhere
    internally. `name` and `aliases` exist only so a human's loosely-worded
    mention can be resolved back to that id.
    """

    category_id: int
    name: str
    aliases: list[str] = Field(default_factory=list)


class MetricPoint(BaseModel):
    """One metric's value for one category, at one site, on one day."""

    category_id: int
    site_id: int
    metric_key: str
    date: date
    value: float


class CategorySnapshot(BaseModel):
    """All metrics for one category at one site on one day.

    Metrics are a `dict[str, float]` keyed by metric key rather than one
    field per metric, so adding a metric to the registry never requires a
    model change here.
    """

    category_id: int
    site_id: int
    date: date
    metrics: dict[str, float]


class DateRange(BaseModel):
    """An inclusive date range, optionally carrying the phrase it came from.

    `label` (e.g. `"last week"`) lets the agent echo back what it
    understood the user to mean instead of silently substituting dates.
    """

    start: date
    end: date
    label: str | None = None

    @model_validator(mode="after")
    def _check_start_before_end(self) -> "DateRange":
        if self.start > self.end:
            raise ValueError(f"DateRange start ({self.start}) is after end ({self.end}).")
        return self


class PeriodComparison(BaseModel):
    """The result of comparing one metric across two periods.

    Convention: `period_a` is the earlier/baseline period, `period_b` is
    the later/comparison period. `pct_delta` is
    `(value_b - value_a) / value_a`. `improved` accounts for the metric's
    `TrendDirection` — a drop in a lower-is-better metric is an
    improvement.
    """

    category_id: int
    site_id: int
    metric_key: str
    period_a: DateRange
    period_b: DateRange
    value_a: float
    value_b: float
    absolute_delta: float
    pct_delta: float
    improved: bool


class Note(BaseModel):
    """A raw analyst note from the corpus, before indexing or retrieval."""

    category_id: int
    date: date
    body: str


class NoteChunk(BaseModel):
    """A retrieved, scored chunk of a note.

    Separate from `Note` (rather than giving `Note` an optional `score`)
    because a chunk only has a similarity score *after* retrieval — this
    keeps the ingestion path from carrying an always-empty field.
    """

    category_id: int
    date: date
    body: str
    score: float
    chunk_id: str | None = None


class QueryIntent(BaseModel):
    """Structured intent extracted from a free-text question.

    `category_mention` is deliberately the user's raw text, not a resolved
    id — resolution is a separate graph step, so extraction and resolution
    can be reasoned about and tested independently.
    """

    category_mention: str | None
    site_mention: str | None = None
    metric_keys: list[str] = Field(default_factory=list)
    date_range: DateRange | None = None
    comparison_range: DateRange | None = None
    wants_explanation: bool = False
    raw_question: str


class CategoryMatch(BaseModel):
    """A candidate resolution of a category mention, with a confidence tier."""

    category_id: int
    name: str
    score: float
    confidence: Literal["high", "medium", "low"]
