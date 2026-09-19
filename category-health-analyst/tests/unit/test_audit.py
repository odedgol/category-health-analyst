from datetime import date

import pytest
from category_health.audit import (
    AuditStatus,
    AuditTrail,
    InMemoryAuditSink,
    current_audit,
)
from category_health.domain.query import AnalysisQuery, QueryIntent
from category_health.domain.models import DateRange


def trend_query() -> AnalysisQuery:
    return AnalysisQuery(
        intent=QueryIntent.TREND,
        metric_ids=("image_count",),
        category_id=20081,
        site_ids=(77,),
        date_range=DateRange(
            start=date(2026, 9, 9),
            end=date(2026, 9, 10),
        ),
    )


def test_successful_step_records_started_and_succeeded_events() -> None:
    sink = InMemoryAuditSink()
    audit = AuditTrail(sink)

    with audit.step("resolve_category", {"mention": "Antiques"}) as step:
        step.set_output({"category_id": 20081})

    events = sink.for_trace(audit.trace_id)

    assert [event.status for event in events] == [AuditStatus.STARTED, AuditStatus.SUCCEEDED]
    assert [event.sequence for event in events] == [1, 2]
    assert events[1].output_summary == {"category_id": 20081}
    assert events[1].duration_ms is not None


def test_failed_step_records_error_and_reraises() -> None:
    sink = InMemoryAuditSink()
    audit = AuditTrail(sink)

    with pytest.raises(ValueError, match="bad category"), audit.step("resolve_category"):
        raise ValueError("bad category")

    events = sink.for_trace(audit.trace_id)

    assert events[-1].status == AuditStatus.FAILED
    assert events[-1].error_type == "ValueError"
    assert events[-1].error_message == "bad category"


def test_audit_trail_is_current_only_inside_explicit_scope() -> None:
    audit = AuditTrail(InMemoryAuditSink())

    assert current_audit.get() is None
    with audit.as_current():
        assert current_audit.get() is audit
    assert current_audit.get() is None


def test_traces_are_isolated() -> None:
    sink = InMemoryAuditSink()
    first = AuditTrail(sink)
    second = AuditTrail(sink)

    with first.step("first"):
        pass
    with second.step("second"):
        pass

    assert [event.step for event in sink.for_trace(first.trace_id)] == ["first", "first"]
    assert [event.step for event in sink.for_trace(second.trace_id)] == ["second", "second"]


def test_domain_objects_are_recorded_as_json_safe_snapshots() -> None:
    sink = InMemoryAuditSink()
    audit = AuditTrail(sink)
    query = trend_query()

    with audit.step("validate_query", input_object=query) as step:
        step.set_output_object(query)

    events = sink.for_trace(audit.trace_id)

    assert events[0].input_object["intent"] == "trend"
    assert events[1].output_object["category_id"] == 20081


def test_lists_of_domain_objects_are_recorded_as_structured_data() -> None:
    sink = InMemoryAuditSink()
    audit = AuditTrail(sink)
    query = trend_query()

    with audit.step("retrieve_updates") as step:
        step.set_output_object([query])

    event = sink.for_trace(audit.trace_id)[1]

    assert event.output_object[0]["category_id"] == 20081
