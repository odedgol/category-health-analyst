"""Optional OpenTelemetry-native Langfuse visibility for business audit steps."""

import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from category_health.audit import (
    AuditEvent,
    AuditSummary,
    JsonlAuditSink,
    StepAuditContext,
)


class LangfuseClient(Protocol):
    """Small SDK boundary so observability behavior is testable without a network."""

    def get_current_trace_id(self) -> str | None: ...

    def start_as_current_observation(self, **kwargs): ...

    def update_current_span(self, **kwargs) -> None: ...

    def get_trace_url(self, *, trace_id: str) -> str: ...

    def flush(self) -> None: ...


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LangfuseSettings:
    """Environment-derived configuration; credentials never enter audit records."""

    public_key: str | None
    secret_key: str | None
    base_url: str
    capture_objects: bool = False
    environment: str = "local"
    version: str = "0.1.0"
    service_name: str = "category-health-analyst"

    @property
    def configured(self) -> bool:
        return bool(self.public_key and self.secret_key)

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "LangfuseSettings":
        values = environment if environment is not None else os.environ
        return cls(
            public_key=values.get("LANGFUSE_PUBLIC_KEY"),
            secret_key=values.get("LANGFUSE_SECRET_KEY"),
            base_url=values.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/"),
            capture_objects=_is_true(values.get("CATEGORY_HEALTH_TELEMETRY_CAPTURE_OBJECTS")),
            environment=values.get("LANGFUSE_TRACING_ENVIRONMENT", "local"),
            version=values.get("CATEGORY_HEALTH_APP_VERSION", "0.1.0"),
            service_name=values.get("OTEL_SERVICE_NAME", "category-health-analyst"),
        )


class LangfuseStepObserver:
    """Map each nested ``AuditTrail.step`` context to one Langfuse/OTel span."""

    def __init__(
        self,
        client: LangfuseClient,
        settings: LangfuseSettings,
        attribute_context_factory: Callable[..., AbstractContextManager] | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.attribute_context_factory = attribute_context_factory
        self._depth: ContextVar[int] = ContextVar(
            f"langfuse_audit_depth_{id(self)}", default=0
        )

    @staticmethod
    def _observation_type(name: str) -> str:
        if name == "user_request":
            return "agent"
        if name == "mcp_tool_call":
            return "tool"
        return "span"

    def _payload(
        self,
        name: str,
        summary: AuditSummary,
        value: object | None,
    ) -> object:
        payload: dict[str, object] = {"summary": summary}
        root_objects_are_safe = name in {"user_request", "mcp_tool_call"}
        if (self.settings.capture_objects or root_objects_are_safe) and value is not None:
            payload["object"] = value
        return payload

    def current_trace_uuid(self) -> UUID | None:
        """Return the active OTel/Langfuse trace ID when called below an integration."""

        try:
            trace_id = self.client.get_current_trace_id()
            return UUID(hex=trace_id) if trace_id else None
        except Exception:
            return None

    def update_active_span(self, **kwargs) -> None:
        """Enrich an upstream integration span without making telemetry authoritative."""

        try:
            self.client.update_current_span(**kwargs)
        except Exception:
            pass

    @contextmanager
    def observe_step(
        self,
        *,
        trace_id: UUID,
        name: str,
        input_summary: AuditSummary,
        input_object: object | None,
        step_context: StepAuditContext,
        trace_name: str | None = None,
        session_id: str | None = None,
        tags: tuple[str, ...] = (),
    ) -> Iterator[None]:
        """Create a span while ensuring telemetry failures never break the agent."""

        stack = None
        observation = None
        depth_token = None
        try:
            stack = ExitStack()
            is_root = self._depth.get() == 0
            active_trace_id = self.client.get_current_trace_id() if is_root else None
            trace_context = {"trace_id": trace_id.hex} if is_root and not active_trace_id else None
            attributes_context = (
                self.attribute_context_factory(
                    trace_name=trace_name,
                    session_id=session_id,
                    tags=list(tags) or None,
                    version=self.settings.version,
                    environment=self.settings.environment,
                    metadata={"businessTraceId": str(trace_id)},
                )
                if is_root and self.attribute_context_factory is not None
                else nullcontext()
            )
            if active_trace_id:
                stack.enter_context(attributes_context)
            observation = stack.enter_context(
                self.client.start_as_current_observation(
                    trace_context=trace_context,
                    name=name,
                    as_type=self._observation_type(name),
                    input=self._payload(name, input_summary, input_object),
                    metadata={"businessTraceId": str(trace_id)},
                )
            )
            if not active_trace_id:
                stack.enter_context(attributes_context)
            depth_token = self._depth.set(self._depth.get() + 1)
        except Exception:
            if stack is not None:
                stack.close()
            stack = None

        error: Exception | None = None
        try:
            yield
        except Exception as caught:
            error = caught
            if observation is not None:
                try:
                    observation.update(
                        output=self._payload(
                            name,
                            step_context.output_summary,
                            step_context.output_object,
                        ),
                        level="ERROR",
                        status_message=f"{type(caught).__name__}: {caught}",
                    )
                except Exception:
                    pass
            raise
        else:
            if observation is not None:
                try:
                    observation.update(
                        output=self._payload(
                            name,
                            step_context.output_summary,
                            step_context.output_object,
                        )
                    )
                except Exception:
                    pass
        finally:
            if stack is not None:
                try:
                    if error is None:
                        stack.__exit__(None, None, None)
                    else:
                        stack.__exit__(type(error), error, error.__traceback__)
                except Exception:
                    pass
            if depth_token is not None:
                self._depth.reset(depth_token)

    def trace_url(self, trace_id: UUID) -> str | None:
        try:
            return self.client.get_trace_url(trace_id=trace_id.hex)
        except Exception:
            return None

    def flush(self) -> None:
        try:
            self.client.flush()
        except Exception:
            pass


class CompositeAuditSink:
    """Keep JSONL authoritative and add an optional, fail-open span observer."""

    def __init__(
        self,
        primary: JsonlAuditSink,
        observer: LangfuseStepObserver | None = None,
        langchain_callback: object | None = None,
    ) -> None:
        self.primary = primary
        self.observer = observer
        self.langchain_callback = langchain_callback

    @property
    def path(self) -> Path:
        return self.primary.path

    @property
    def events(self) -> list[AuditEvent]:
        return self.primary.events

    @property
    def telemetry_enabled(self) -> bool:
        return self.observer is not None

    def record(self, event: AuditEvent) -> None:
        self.primary.record(event)

    def for_trace(self, trace_id: UUID) -> list[AuditEvent]:
        return self.primary.for_trace(trace_id)

    @contextmanager
    def observe_step(self, **kwargs) -> Iterator[None]:
        if self.observer is None:
            yield
            return
        with self.observer.observe_step(**kwargs):
            yield

    def trace_url(self, trace_id: UUID) -> str | None:
        return self.observer.trace_url(trace_id) if self.observer else None

    def current_trace_uuid(self) -> UUID | None:
        return self.observer.current_trace_uuid() if self.observer else None

    def update_active_span(self, **kwargs) -> None:
        if self.observer:
            self.observer.update_active_span(**kwargs)

    def langchain_callbacks(self) -> list[object]:
        """Return callbacks that enrich the current OTel trace with model activity."""

        return [self.langchain_callback] if self.langchain_callback is not None else []

    def flush(self) -> None:
        if self.observer:
            self.observer.flush()


def create_audit_sink(
    path: Path,
    *,
    environment: Mapping[str, str] | None = None,
    client: LangfuseClient | None = None,
    attribute_context_factory: Callable[..., AbstractContextManager] | None = None,
) -> CompositeAuditSink:
    """Create the durable local sink and enable Langfuse only when configured."""

    settings = LangfuseSettings.from_environment(environment)
    observer = None
    langchain_callback = None
    if settings.configured:
        try:
            from langfuse import Langfuse, propagate_attributes

            attribute_context_factory = (
                attribute_context_factory or propagate_attributes
            )
            if client is None:
                from langfuse.langchain import CallbackHandler

                os.environ.setdefault("OTEL_SERVICE_NAME", settings.service_name)
                client = Langfuse(
                    public_key=settings.public_key,
                    secret_key=settings.secret_key,
                    base_url=settings.base_url,
                    tracing_enabled=True,
                    environment=settings.environment,
                )
                langchain_callback = CallbackHandler(public_key=settings.public_key)
            observer = LangfuseStepObserver(
                client,
                settings,
                attribute_context_factory=attribute_context_factory,
            )
        except Exception:
            observer = None
            langchain_callback = None
    return CompositeAuditSink(JsonlAuditSink(path), observer, langchain_callback)
