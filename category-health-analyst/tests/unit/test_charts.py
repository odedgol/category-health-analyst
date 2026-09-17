from category_health.charts import build_chart_specs


SITE_LABELS = {77: "Germany", 3: "UK"}
METRIC_LABELS = {
    "image_coverage_percentage": "Image coverage percentage",
    "image_count": "Image count",
    "has_title": "Has title",
}


def build(values, status="ok"):
    return build_chart_specs(
        {"status": status, "values": values},
        site_labels=SITE_LABELS,
        metric_labels=METRIC_LABELS,
    )


def test_trend_builds_percentage_line_chart() -> None:
    charts = build(
        [
            {
                "site_id": 77,
                "period": "current",
                "observed_date": "2026-09-09",
                "metric_id": "image_coverage_percentage",
                "value": "72.0000",
            },
            {
                "site_id": 77,
                "period": "current",
                "observed_date": "2026-09-10",
                "metric_id": "image_coverage_percentage",
                "value": "64.0000",
            },
        ]
    )

    assert len(charts) == 1
    assert charts[0]["kind"] == "line"
    assert charts[0]["y_label"] == "Percentage (%)"
    assert [row["Value"] for row in charts[0]["rows"]] == [72.0, 64.0]


def test_same_date_site_comparison_builds_multiple_series_bar_chart() -> None:
    charts = build(
        [
            {
                "site_id": 77,
                "period": "current",
                "observed_date": "2026-09-10",
                "metric_id": "image_count",
                "value": 219,
            },
            {
                "site_id": 3,
                "period": "current",
                "observed_date": "2026-09-10",
                "metric_id": "image_count",
                "value": 229,
            },
        ]
    )

    assert charts[0]["kind"] == "bar"
    assert charts[0]["multiple_series"] is True
    assert {row["Series"] for row in charts[0]["rows"]} == {"Germany", "UK"}


def test_boolean_chart_and_no_data_behavior() -> None:
    charts = build(
        [
            {
                "site_id": 77,
                "period": "current",
                "observed_date": "2026-09-09",
                "metric_id": "has_title",
                "value": False,
            },
            {
                "site_id": 77,
                "period": "current",
                "observed_date": "2026-09-10",
                "metric_id": "has_title",
                "value": True,
            },
        ]
    )

    assert charts[0]["y_label"] == "State (0 = false, 1 = true)"
    assert [row["Value"] for row in charts[0]["rows"]] == [0.0, 1.0]
    assert build([], status="no_data") == []
