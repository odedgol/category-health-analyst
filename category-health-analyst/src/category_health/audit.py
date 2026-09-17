"""Trace-scoped audit events for analyzing the full request flow."""

import json
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

AuditValue = str | int | float | bool | None
AuditSummary = dict[str, AuditValue]


def serialize_object(value: object | None) -> object | None:
    """Convert a domain object into a JSON-safe audit snapshot."""

    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return serialize_object(asdict(value))
    if isinstance(value, dict):
        return {str(key): serialize_object(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_object(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode(errors="replace")
    return json.loads(json.dumps(str(value)))


class AuditStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AuditEvent(BaseModel):
    """One immutable event in a request trace."""

    event_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    sequence: int = Field(ge=1)
    step: str
    status: AuditStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    input_summary: AuditSummary = Field(default_factory=dict)
    output_summary: AuditSummary = Field(default_factory=dict)
    input_object: object | None = None
    output_object: object | None = None
    error_type: str | None = None
    error_message: str | None = None


class AuditSink(Protocol):
    """Destination for audit events."""

    def record(self, event: AuditEvent) -> None:
        """Persist one audit event."""


class InMemoryAuditSink:
    """Simple audit destination for tests and local development."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> None:
        self.events.append(event)

    def for_trace(self, trace_id: UUID) -> list[AuditEvent]:
        return [event for event in self.events if event.trace_id == trace_id]


class JsonlAuditSink(InMemoryAuditSink):
    """Append each event immediately to a local file, retaining CLI visibility."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def record(self, event: AuditEvent) -> None:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")
            super().record(event)


current_audit: ContextVar["AuditTrail | None"] = ContextVar("current_audit", default=None)


class StepAuditContext:
    """Mutable output-summary holder used only during one step."""

    def __init__(self) -> None:
        self.output_summary: AuditSummary = {}
        self.output_object: object | None = None

    def set_output(self, summary: AuditSummary) -> None:
        self.output_summary = summary

    def set_output_object(self, value: object) -> None:
        self.output_object = serialize_object(value)


class AuditTrail:
    """Create ordered audit events for one user request."""

    def __init__(
        self,
        sink: AuditSink,
        trace_id: UUID | None = None,
        *,
        trace_name: str | None = None,
        session_id: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> None:
        self.sink = sink
        self.trace_id = trace_id or uuid4()
        self.trace_name = trace_name
        self.session_id = session_id
        self.tags = tags
        self._sequence = 0
        self._lock = RLock()

    def _next_sequence(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    @contextmanager
    def step(
        self,
        name: str,
        input_summary: AuditSummary | None = None,
        input_object: object | None = None,
    ) -> Iterator[StepAuditContext]:
        """Audit one logical step and preserve failures before re-raising them."""

        started_at = datetime.now(UTC)
        start_clock = perf_counter()
        inputs = input_summary or {}
        input_snapshot = serialize_object(input_object)
        context = StepAuditContext()
        observe_step = getattr(self.sink, "observe_step", None)
        observation = (
            observe_step(
                trace_id=self.trace_id,
                name=name,
                input_summary=inputs,
                input_object=input_snapshot,
                step_context=context,
                trace_name=self.trace_name,
                session_id=self.session_id,
                tags=self.tags,
            )
            if callable(observe_step)
            else nullcontext()
        )

        with observation:
            self.sink.record(
                AuditEvent(
                    trace_id=self.trace_id,
                    sequence=self._next_sequence(),
                    step=name,
                    status=AuditStatus.STARTED,
                    started_at=started_at,
                    input_summary=inputs,
                    input_object=input_snapshot,
                )
            )
            try:
                yield context
            except Exception as error:
                completed_at = datetime.now(UTC)
                self.sink.record(
                    AuditEvent(
                        trace_id=self.trace_id,
                        sequence=self._next_sequence(),
                        step=name,
                        status=AuditStatus.FAILED,
                        started_at=started_at,
                        completed_at=completed_at,
                        duration_ms=(perf_counter() - start_clock) * 1000,
                        input_summary=inputs,
                        output_summary=context.output_summary,
                        input_object=input_snapshot,
                        output_object=context.output_object,
                        error_type=type(error).__name__,
                        error_message=str(error),
                    )
                )
                raise
            else:
                completed_at = datetime.now(UTC)
                self.sink.record(
                    AuditEvent(
                        trace_id=self.trace_id,
                        sequence=self._next_sequence(),
                        step=name,
                        status=AuditStatus.SUCCEEDED,
                        started_at=started_at,
                        completed_at=completed_at,
                        duration_ms=(perf_counter() - start_clock) * 1000,
                        input_summary=inputs,
                        output_summary=context.output_summary,
                        input_object=input_snapshot,
                        output_object=context.output_object,
                    )
                )
