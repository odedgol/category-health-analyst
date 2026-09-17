"""Validated structured requests that can be passed to planning code."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from category_health.domain.models import DateRange


class QueryIntent(StrEnum):
    SNAPSHOT = "snapshot"
    TREND = "trend"
    COMPARE_PERIODS = "compare_periods"
    COMPARE_SITES = "compare_sites"
    EXPLAIN_CHANGE = "explain_change"


class AnalyticsQuerySpec(BaseModel):
    """The validated intermediate representation of one analytical request."""

    intent: QueryIntent
    metric_ids: tuple[str, ...] = Field(min_length=1)
    category_id: int | None = Field(default=None, ge=0)
    site_ids: tuple[int, ...] = Field(default=(), min_length=1)
    date_range: DateRange | None = None
    comparison_range: DateRange | None = None
    unresolved_fields: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_intent_requirements(self) -> "AnalyticsQuerySpec":
        if (
            self.intent == QueryIntent.COMPARE_PERIODS
            and (self.date_range is None or self.comparison_range is None)
        ):
            raise ValueError("compare_periods requires date_range and comparison_range")

        if self.intent == QueryIntent.COMPARE_SITES and len(set(self.site_ids)) != 2:
            raise ValueError("compare_sites requires exactly two site IDs")

        return self

    @property
    def is_executable(self) -> bool:
        """Whether the spec has enough information to reach the planner."""

        return self.category_id is not None and bool(self.site_ids) and not self.unresolved_fields
