"""Behavioral regressions across both repository adapters, without model calls."""

import json
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import duckdb
import pytest
from category_health.application.analysis import CategoryHealthAnalyzer
from category_health.agent.deep_agent import create_analysis_tool
from category_health.agent.session import AnalysisSession
from category_health.application.requests import AnalysisRequest
from category_health.application.service import CategoryHealthService
from category_health.audit import (
    AuditEvent,
    AuditTrail,
    InMemoryAuditSink,
    JsonlAuditSink,
    current_audit,
)
from category_health.catalogs.catalogs import (
    MetricCatalog,
    MetricDefinition,
    SiteCatalog,
    SiteDefinition,
)
from category_health.catalogs.categories import CategoryCatalog, CategoryDefinition
from category_health.domain.models import CategorySiteMetrics, DateRange
from category_health.domain.query import AnalysisQuery
from category_health.repositories.duckdb import DuckDbMetricsRepository
from category_health.repositories.in_memory import InMemoryMetricsRepository
from category_health.repositories.mock_data import seed_mock_data
from pydantic import ValidationError


@pytest.fixture(params=["memory", "duckdb"])
def repository(request):
    if request.param == "memory":
        yield InMemoryMetricsRepository()
    else:
        connection = duckdb.connect(":memory:")
        yield DuckDbMetricsRepository(connection)
        connection.close()


def row(day, coverage, *, site=77, hour=17, title=True, count=10):
    return CategorySiteMetrics(
        category_id=20081,
        site_id=site,
        observed_date=date(2026, 9, day),
        last_modified_at=datetime(2026, 9, day, hour, tzinfo=UTC),
        active_product_count=100,
        image_count=count,
        has_title=title,
        image_coverage_percentage=Decimal(coverage),
        aligned_aspects_count=450,
        misaligned_aspects_count=50,
        aligned_aspects_percentage=Decimal(90),
        misaligned_aspects_percentage=Decimal(10),
    )


def analyze(
    repository,
    intent="trend",
    metrics=("image_coverage_percentage",),
    sites=(77,),
    start=1,
    end=3,
    comparison=None,
):
    query = AnalysisQuery(
        intent=intent,
        category_id=20081,
        site_ids=sites,
        metric_ids=metrics,
        date_range=DateRange(start=date(2026, 9, start), end=date(2026, 9, end)),
        comparison_range=comparison,
    )
    sink = InMemoryAuditSink()
    return CategoryHealthAnalyzer(repository).analyze(query, AuditTrail(sink))


def test_exact_trend_count_lmd_units_and_booleans(repository):
    for item in (
        row(1, "72"),
        row(2, "90", hour=8),
        row(2, "64", title=False),
        row(3, "70", count=0),
    ):
        repository.add_update(item)
    result = analyze(repository, metrics=("image_coverage_percentage", "image_count", "has_title"))
    assert len(result.comparisons) == 6  # Two adjacent pairs, three metrics; no duplicates.
    percentages = [c for c in result.comparisons if c.metric_id == "image_coverage_percentage"]
    assert [c.delta for c in percentages] == [Decimal(-8), Decimal(6)]
    assert percentages[0].delta_unit == "percentage_points"
    assert percentages[0].current_lmd == datetime(2026, 9, 2, 17, tzinfo=UTC)
    boolean = next(c for c in result.comparisons if c.metric_id == "has_title")
    assert boolean.previous_value is True and boolean.current_value is False
    assert boolean.delta is None and boolean.changed
    assert result.status == "ok"


def test_period_comparison_uses_last_snapshot_not_sum(repository):
    for day, value in ((1, "90"), (2, "72"), (3, "80"), (4, "64")):
        repository.add_update(row(day, value))
    response = analyze(
        repository,
        "compare_periods",
        start=3,
        end=4,
        comparison=DateRange(start=date(2026, 9, 1), end=date(2026, 9, 2)),
    )
    assert len(response.comparisons) == 1
    comparison = response.comparisons[0]
    assert (comparison.previous_value, comparison.current_value, comparison.delta) == (72, 64, -8)
    assert comparison.method == "latest_snapshot_per_period"
    assert comparison.previous_date == date(2026, 9, 2)
    assert comparison.current_date == date(2026, 9, 4)


def test_site_comparison_matches_dates_and_reports_missing(repository):
    for item in (row(1, "72"), row(2, "64"), row(2, "80", site=3)):
        repository.add_update(item)
    result = analyze(repository, "compare_sites", sites=(77, 3), end=2)
    assert len(result.comparisons) == 1
    comparison = result.comparisons[0]
    assert comparison.delta == 16
    assert (comparison.previous_site_id, comparison.site_id) == (77, 3)
    assert comparison.previous_date == comparison.current_date == date(2026, 9, 2)
    assert result.status == "partial" and result.warnings


def test_missing_data_is_not_zero_and_change_is_not_causation(repository):
    empty = analyze(repository)
    assert empty.status == "no_data" and not empty.comparisons
    repository.add_update(row(1, "0"))
    single = analyze(repository)
    assert single.values[0].value == 0 and not single.comparisons
    repository.add_update(row(3, "10"))
    changed = analyze(repository, "explain_change")
    assert len(changed.comparisons) == 1 and changed.comparisons[0].delta == 10
    assert any("causes" in warning for warning in changed.warnings)
    assert any("missing" in warning for warning in changed.warnings)


def test_no_data_reports_the_repositorys_available_date_range(repository):
    repository.add_update(row(1, "72"))
    repository.add_update(row(3, "64"))

    assert repository.available_date_range(20081, 77) == DateRange(
        start=date(2026, 9, 1), end=date(2026, 9, 3)
    )
    response = analyze(repository, start=4, end=5)

    assert response.status == "no_data"
    assert any(
        "Available dates for site 77: 2026-09-01 through 2026-09-03" in warning
        for warning in response.warnings
    )


def test_snapshot_respects_date_range(repository):
    repository.add_update(row(1, "72"))
    repository.add_update(row(3, "64"))
    response = analyze(repository, "snapshot", end=1)
    assert len(response.values) == 1 and response.values[0].value == 72
    assert response.status == "ok"


def test_timezone_roundtrip(repository):
    local = row(1, "72")
    local.last_modified_at = datetime(2026, 9, 1, 20, tzinfo=timezone(timedelta(hours=3)))
    repository.add_update(local)
    fetched = repository.latest_per_day(
        20081, 77, DateRange(start=date(2026, 9, 1), end=date(2026, 9, 1))
    )[0]
    assert fetched.last_modified_at == datetime(2026, 9, 1, 17, tzinfo=UTC)


def test_mock_supports_thirty_day_queries(repository):
    seed_mock_data(repository)
    query = AnalysisQuery(
        intent="trend",
        category_id=20081,
        site_ids=(77,),
        metric_ids=("image_count",),
        date_range=DateRange(start=date(2026, 8, 12), end=date(2026, 9, 10)),
    )
    sink = InMemoryAuditSink()
    response = CategoryHealthAnalyzer(repository).analyze(query, AuditTrail(sink))
    assert len(response.values) == 30 and len(response.comparisons) == 29
    assert response.status == "ok"


@pytest.mark.parametrize(
    "changes",
    [
        {"start_date": None},
        {"end_date": "2026-08-01"},
        {"intent": "compare_periods"},
        {"start_date": "2024-01-01"},
        {"comparison_start_date": "2026-08-01"},
        {"sites": [" "]},
        {"metrics": []},
        {"unexpected": "field"},
        {"intent": "some English sentence"},
    ],
)
def test_invalid_requests_are_rejected(changes):
    args = dict(
        intent="trend",
        category="20081",
        sites=["Germany"],
        metrics=["image coverage"],
        start_date="2026-09-01",
        end_date="2026-09-03",
    )
    args.update(changes)
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate(args)


def make_tool(repository, sink):
    service = CategoryHealthService(
        repository=repository,
        category_catalog=CategoryCatalog(
            (
                CategoryDefinition(20081, "Antiques"),
                CategoryDefinition(1, "Armor"),
                CategoryDefinition(2, "Armor"),
            )
        ),
        site_catalog=SiteCatalog(
            (SiteDefinition(77, "Germany", "Germany", "DE", ()),)
        ),
        metric_catalog=MetricCatalog(
            (
                MetricDefinition(
                    "image_coverage_percentage", "Image coverage", "%", ("image coverage",)
                ),
            )
        ),
        audit_sink=sink,
    )
    return create_analysis_tool(service, sink)


def test_clarification_retry_history_and_persistent_audit(repository, tmp_path):
    repository.add_update(row(1, "72"))
    repository.add_update(row(2, "64"))
    sink = JsonlAuditSink(tmp_path / "events.jsonl")
    tool = make_tool(repository, sink)

    class ScriptedAgent:
        calls = 0

        def invoke(self, payload, config):
            self.calls += 1
            assert config["recursion_limit"] == 20
            if self.calls == 2:
                assert len(payload["messages"]) == 3  # prior user + assistant + follow-up
            args = dict(
                intent="trend",
                category="Armor",
                sites=["Germany"],
                metrics=["image coverage"],
                start_date="2026-09-01",
                end_date="2026-09-02",
            )
            rejected = tool(**args)
            assert rejected["status"] == "needs_clarification"
            assert "1, 2" in rejected["message"]
            args["category"] = "20081"
            accepted = tool(**args)
            assert accepted["trace_id"] == rejected["trace_id"]
            assert len(accepted["comparisons"]) == 1
            return {
                "messages": [*payload["messages"], SimpleNamespace(content="Coverage fell by 8 pp")]
            }

    session = AnalysisSession(ScriptedAgent(), sink)
    session.ask("Show the trend")
    first_trace = session.last_trace_id
    session.ask("And again?")
    assert session.last_trace_id != first_trace and current_audit.get() is None
    first = sink.for_trace(first_trace)
    assert sorted(e.sequence for e in first) == list(range(1, len(first) + 1))
    assert any(e.status.value == "failed" for e in first)
    projected = next(
        e for e in first if e.step == "calculate_and_project" and e.status.value == "succeeded"
    )
    assert Decimal(projected.output_object["comparisons"][0]["delta"]) == -8
    assert any(e.step == "final_answer" for e in first)
    persisted = [
        AuditEvent.model_validate(json.loads(line)) for line in sink.path.read_text().splitlines()
    ]
    assert len(persisted) == len(sink.events)


def test_failed_turn_keeps_history_and_records_failure(tmp_path):
    class BrokenAgent:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("upstream unavailable")

    sink = JsonlAuditSink(tmp_path / "events.jsonl")
    session = AnalysisSession(BrokenAgent(), sink)
    with pytest.raises(RuntimeError):
        session.ask("Show coverage")
    assert session.messages == [] and current_audit.get() is None
    assert sink.events[-1].status.value == "failed"


def test_real_framework_propagates_audit_through_tool_execution(monkeypatch, tmp_path):
    from category_health.agent.deep_agent import create_category_health_deep_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage, ToolMessage

    class LocalModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            names = [t.name for t in tools]
            assert names == ["analyze_category_health", "list_available_metrics"]
            return self

        def get_num_tokens_from_messages(self, messages, tools=None):
            return 100

    model = LocalModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "analyze_category_health",
                        "id": "test-call",
                        "args": {
                            "intent": "trend",
                            "category": "20081",
                            "sites": ["Germany"],
                            "metrics": ["image coverage"],
                            "start_date": "2026-09-09",
                            "end_date": "2026-09-10",
                        },
                    }
                ],
            ),
            AIMessage(content="Coverage decreased by 8 percentage points."),
        ]
    )
    monkeypatch.setattr("deepagents.graph.resolve_model", lambda _: model)
    repository = InMemoryMetricsRepository()
    seed_mock_data(repository)
    sink = JsonlAuditSink(tmp_path / "graph.jsonl")
    service = CategoryHealthService(
        repository=repository,
        category_catalog=CategoryCatalog((CategoryDefinition(20081, "Antiques"),)),
        site_catalog=SiteCatalog(
            (SiteDefinition(77, "Germany", "Germany", "DE", ()),)
        ),
        metric_catalog=MetricCatalog(
            (MetricDefinition("image_coverage_percentage", "Image coverage", "%", ()),)
        ),
        audit_sink=sink,
    )
    graph = create_category_health_deep_agent(
        model="openai:category-health-test",
        service=service,
        audit_sink=sink,
    )
    session = AnalysisSession(graph, sink)
    answer = session.ask("Show coverage September 9–10")
    assert "8" in answer.content
    tool_message = next(m for m in session.messages if isinstance(m, ToolMessage))
    payload = json.loads(tool_message.content)
    assert payload["trace_id"] == str(session.last_trace_id)
    assert Decimal(payload["comparisons"][0]["delta"]) == -8
    assert session.last_analysis_output == payload
    assert {e.trace_id for e in sink.events} == {session.last_trace_id}


def test_naive_lmd_is_rejected():
    source = row(1, "72").model_dump()
    source["last_modified_at"] = datetime(2026, 9, 1, 17)
    with pytest.raises(ValidationError, match="timezone"):
        CategorySiteMetrics.model_validate(source)
