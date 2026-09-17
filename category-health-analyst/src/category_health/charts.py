"""Build deterministic chart specifications from structured analysis output."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


def _numeric_value(value: object) -> tuple[float, bool] | None:
    if isinstance(value, bool):
        return float(value), True
    if value is None:
        return None
    try:
        return float(Decimal(str(value))), False
    except InvalidOperation:
        return None


def build_chart_specs(
    output: object,
    *,
    site_labels: dict[int, str],
    metric_labels: dict[str, str],
) -> list[dict[str, Any]]:
    """Group structured values into one unit-safe chart per metric."""

    if not isinstance(output, dict) or output.get("status") not in {"ok", "partial"}:
        return []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in output.get("values", []):
        if not isinstance(item, dict) or not item.get("observed_date"):
            continue
        numeric = _numeric_value(item.get("value"))
        if numeric is None:
            continue
        value, is_boolean = numeric
        metric_id = str(item.get("metric_id", "metric"))
        site_id = int(item["site_id"])
        period = str(item.get("period", "current"))
        grouped[metric_id].append(
            {
                "Date": date.fromisoformat(str(item["observed_date"])),
                "Value": value,
                "Site": site_labels.get(site_id, f"Site {site_id}"),
                "Period": period.replace("_", " ").title(),
                "Boolean": is_boolean,
            }
        )

    specs = []
    for metric_id, values in grouped.items():
        sites = {str(row["Site"]) for row in values}
        periods = {str(row["Period"]) for row in values}
        for row in values:
            parts = []
            if len(sites) > 1:
                parts.append(str(row["Site"]))
            if len(periods) > 1:
                parts.append(str(row["Period"]))
            row["Series"] = " · ".join(parts) or metric_labels.get(
                metric_id, metric_id.replace("_", " ").title()
            )
        boolean_metric = all(bool(row.pop("Boolean")) for row in values)
        unique_dates = {row["Date"] for row in values}
        specs.append(
            {
                "metric_id": metric_id,
                "title": metric_labels.get(
                    metric_id, metric_id.replace("_", " ").title()
                ),
                "y_label": (
                    "State (0 = false, 1 = true)"
                    if boolean_metric
                    else "Percentage (%)"
                    if "percentage" in metric_id
                    else "Count"
                ),
                "kind": "line" if len(unique_dates) > 1 else "bar",
                "multiple_series": len({str(row["Series"]) for row in values}) > 1,
                "rows": sorted(values, key=lambda row: (row["Date"], row["Series"])),
            }
        )
    return specs
