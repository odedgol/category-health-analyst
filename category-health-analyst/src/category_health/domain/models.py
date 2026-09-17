"""Domain models for stored category-health observations.

These models describe business meaning, not database tables. They deliberately
have no imports from database, web, LLM, or UI frameworks.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class Site(BaseModel):
    """An eBay marketplace/site with user-facing aliases."""

    site_id: int = Field(ge=0)
    name: str
    country: str
    aliases: tuple[str, ...] = ()


class DateRange(BaseModel):
    """An inclusive calendar date range."""

    start: date
    end: date

    @model_validator(mode="after")
    def validate_order(self) -> "DateRange":
        if self.start > self.end:
            raise ValueError("DateRange.start must not be after DateRange.end")
        return self


class CategorySiteMetrics(BaseModel):
    """Aggregated metrics stored for one category/site update."""

    category_id: int = Field(ge=0)
    site_id: int = Field(ge=0)
    observed_date: date
    last_modified_at: datetime
    active_product_count: int = Field(ge=0)
    image_coverage_percentage: Decimal = Field(ge=0, le=100)
    image_count: int = Field(ge=0)
    has_title: bool
    aligned_aspects_count: int = Field(ge=0)
    misaligned_aspects_count: int = Field(ge=0)
    aligned_aspects_percentage: Decimal = Field(ge=0, le=100)
    misaligned_aspects_percentage: Decimal = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_business_rules(self) -> "CategorySiteMetrics":
        if self.last_modified_at.utcoffset() is None:
            raise ValueError("last_modified_at must include a timezone")
        if self.active_product_count == 0 and self.image_coverage_percentage != 0:
            raise ValueError(
                "image_coverage_percentage must be 0 when active_product_count is 0"
            )

        total_aspects = self.aligned_aspects_count + self.misaligned_aspects_count
        percentage_sum = (
            self.aligned_aspects_percentage + self.misaligned_aspects_percentage
        )
        if total_aspects > 0 and abs(percentage_sum - 100) > Decimal("0.01"):
            raise ValueError(
                "aligned and misaligned aspect percentages must add up to 100"
            )

        if self.last_modified_at.date() < self.observed_date:
            raise ValueError("last_modified_at cannot be before observed_date")

        return self


class MetricComparison(BaseModel):
    """A comparison calculated by the analyst from two stored updates."""

    previous_value: Decimal
    current_value: Decimal
    absolute_delta: Decimal
    percentage_point_delta: Decimal
