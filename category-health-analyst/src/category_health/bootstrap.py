"""Composition root for the local, reproducible category-health runtime."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from category_health.application.service import CategoryHealthService
from category_health.agent.deep_agent import create_category_health_deep_agent
from category_health.agent.session import AnalysisSession
from category_health.catalogs.catalogs import (
    MetricCatalog,
    SiteCatalog,
    load_metric_catalog,
    load_site_catalog,
)
from category_health.catalogs.categories import CategoryCatalog, load_category_catalog
from category_health.config import load_local_environment
from category_health.observability import CompositeAuditSink, create_audit_sink
from category_health.model_provider import (
    ModelSettings,
    build_agent_model,
    load_model_settings,
)
from category_health.repositories.duckdb import DuckDbMetricsRepository
from category_health.repositories.mock_data import seed_mock_data
from category_health.tool_adapter import CategoryHealthToolAdapter


@dataclass
class CategoryHealthRuntime:
    """Assembled local dependencies owned by one process or UI session."""

    connection: duckdb.DuckDBPyConnection
    repository: DuckDbMetricsRepository
    category_catalog: CategoryCatalog
    site_catalog: SiteCatalog
    metric_catalog: MetricCatalog
    audit_sink: CompositeAuditSink
    service: CategoryHealthService
    tool_adapter: CategoryHealthToolAdapter

    def close(self) -> None:
        """Flush telemetry and release the process-owned database connection."""

        self.audit_sink.flush()
        self.connection.close()


@dataclass
class ConversationRuntime:
    """A model-backed conversation assembled around the deterministic runtime."""

    application: CategoryHealthRuntime
    model_settings: ModelSettings
    agent: Any
    analysis_session: AnalysisSession
    session_id: str
    trace_name: str
    trace_tags: tuple[str, ...]

    @property
    def audit_sink(self) -> CompositeAuditSink:
        return self.application.audit_sink

    @property
    def site_labels(self) -> dict[int, str]:
        return {
            site.site_id: site.country for site in self.application.site_catalog.sites
        }

    @property
    def metric_labels(self) -> dict[str, str]:
        return {
            metric.metric_id: metric.display_name
            for metric in self.application.metric_catalog.metrics
        }

    def start_new_conversation(self) -> None:
        """Reset model history while retaining the assembled application runtime."""

        self.session_id = str(uuid4())
        self.analysis_session = AnalysisSession(
            self.agent,
            self.audit_sink,
            session_id=self.session_id,
            trace_name=self.trace_name,
            trace_tags=self.trace_tags,
        )

    def close(self) -> None:
        self.application.close()


def create_demo_runtime(
    project_root: Path,
    *,
    audit_path: Path,
    audit_environment: Mapping[str, str] | None = None,
) -> CategoryHealthRuntime:
    """Assemble the local DuckDB and mock-data implementation of the application."""

    load_local_environment(project_root / ".env")
    os.environ.setdefault("OTEL_SERVICE_NAME", "category-health-analyst")

    connection = duckdb.connect(":memory:")
    repository = DuckDbMetricsRepository(connection)
    seed_mock_data(repository)

    category_catalog = load_category_catalog(
        project_root / "data" / "categories_source.txt"
    )
    site_catalog = load_site_catalog(project_root / "data" / "sites.yaml")
    metric_catalog = load_metric_catalog(project_root / "data" / "metrics.yaml")
    audit_sink = create_audit_sink(
        audit_path,
        environment=audit_environment,
    )
    service = CategoryHealthService(
        repository=repository,
        category_catalog=category_catalog,
        site_catalog=site_catalog,
        metric_catalog=metric_catalog,
    )
    tool_adapter = CategoryHealthToolAdapter(service, audit_sink)
    return CategoryHealthRuntime(
        connection=connection,
        repository=repository,
        category_catalog=category_catalog,
        site_catalog=site_catalog,
        metric_catalog=metric_catalog,
        audit_sink=audit_sink,
        service=service,
        tool_adapter=tool_adapter,
    )


def create_demo_conversation_runtime(
    project_root: Path,
    *,
    audit_path: Path,
    source: str,
    session_id: str | None = None,
    model_settings: ModelSettings | None = None,
    audit_environment: Mapping[str, str] | None = None,
) -> ConversationRuntime:
    """Assemble a model-backed conversation around the local demo application."""

    application = create_demo_runtime(
        project_root,
        audit_path=audit_path,
        audit_environment=audit_environment,
    )
    settings = model_settings or load_model_settings()
    agent = create_category_health_deep_agent(
        model=build_agent_model(settings),
        harness_profile_key=settings.harness_profile_key,
        tool_adapter=application.tool_adapter,
    )
    conversation_id = session_id or str(uuid4())
    trace_name = f"category-health-{source}-request"
    trace_tags = ("category-health", source, "mock-data")
    return ConversationRuntime(
        application=application,
        model_settings=settings,
        agent=agent,
        analysis_session=AnalysisSession(
            agent,
            application.audit_sink,
            session_id=conversation_id,
            trace_name=trace_name,
            trace_tags=trace_tags,
        ),
        session_id=conversation_id,
        trace_name=trace_name,
        trace_tags=trace_tags,
    )
