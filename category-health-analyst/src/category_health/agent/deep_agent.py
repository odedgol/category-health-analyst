"""Deep Agents adapter for the deterministic category-health core."""

from collections.abc import Callable
from typing import Annotated, Any

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_core.language_models.chat_models import BaseChatModel

from category_health.application.service import CategoryHealthService
from category_health.audit import AuditSink, AuditTrail, current_audit
from category_health.domain.query import QueryIntent

_BUILT_IN_TOOLS = frozenset(
    {"ls", "read_file", "write_file", "edit_file", "delete", "glob", "grep", "execute", "task"}
)

_SYSTEM_PROMPT = (
    "You are a category-health analyst. Use only the provided domain tools. "
    "Whenever the user asks for metric names, metric options, supported "
    "metrics, available metrics, or what can be analyzed, you MUST call "
    "list_available_metrics and present every returned metric. A catalog "
    "request never requires a category, site, or date. Do not call the catalog "
    "tool merely because an analysis request contains a metric name. For every "
    "analysis request, the metrics array MUST contain only metrics explicitly "
    "requested by the user; never add every metric unless the user explicitly "
    "asks for all metrics. Call analyze_category_health in the current turn; never "
    "promise to analyze later or ask for confirmation when the scope is complete. "
    "Call analyze_category_health even when dates or another field are missing, "
    "using null for missing optional dates, so validation and clarification are audited. "
    "Never ask for missing analysis scope directly: first call the analysis tool, "
    "then relay its needs_clarification response. Never invent category "
    "IDs, site IDs, metrics, or data. Ask for clarification when a catalog "
    "reference is ambiguous. Present the complete available_metrics list whenever "
    "metric clarification is returned. Use the tool's computed comparisons and "
    "never perform numeric comparisons yourself. If any tool returns "
    "needs_clarification, STOP immediately: do not call any analysis tool again "
    "in that turn, do not select an option, and do not guess. Present every "
    "returned option and wait for the user's next message. Reuse explicit scope "
    "from conversation history for follow-up questions. A request such as "
    "'compare image coverage between September 9 and September 10' contains one "
    "range with two endpoint dates: use trend with start_date=September 9 and "
    "end_date=September 10, and leave both comparison dates null. Use "
    "compare_periods only for two complete ranges, such as 'September 9-10 "
    "against September 7-8'; then populate both the primary and comparison ranges. "
    "compare_sites computes sites[1] minus sites[0] on matching dates only. "
    "Therefore wording 'A minus B' MUST be encoded as sites=[B, A]. Explain the "
    "comparison method and units. Report partial/no_data and every warning. For "
    "no_data, clearly distinguish the requested dates from any available-date "
    "range returned in warnings. Never infer, suggest, or speculate about causes "
    "from metric changes alone. Never claim statistical significance because no "
    "statistical test is run. Never label a change positive or negative; state "
    "only increase, decrease, or unchanged. A metric alias successfully resolved "
    "by the tool is supported; never call it unsupported. explain_change describes "
    "first-to-last changes, not causes. compare_periods uses the latest snapshot "
    "in each range, never an average. For 'last N days including today', use "
    "exactly N calendar dates: start=today-(N-1) days and end=today. For example, "
    "with today 2026-09-10, the last two days are 2026-09-09 through 2026-09-10."
)


def create_analysis_tool(
    service: CategoryHealthService,
    audit_sink: AuditSink,
) -> Callable[..., dict[str, Any]]:
    """Expose one application use case as a Deep Agents tool."""

    def analyze_category_health(
        intent: Annotated[
            QueryIntent,
            "Use trend for one date range, including requests to compare a metric "
            "between two individual dates. Use compare_periods only when the user "
            "provides two complete date ranges: a primary range and a comparison range.",
        ],
        category: str,
        sites: Annotated[
            list[str],
            "Only requested sites. For 'A minus B', use [B, A] because the tool computes second minus first.",
        ],
        metrics: Annotated[
            list[str],
            "Only metrics explicitly requested by the user. Never add other catalog metrics unless the user asks for all metrics.",
        ],
        start_date: str | None = None,
        end_date: str | None = None,
        comparison_start_date: str | None = None,
        comparison_end_date: str | None = None,
    ) -> dict[str, Any]:
        """Analyze complete category/site metric rows for the requested scope."""

        audit = current_audit.get() or AuditTrail(audit_sink)
        return service.analyze_arguments(
            {
                "intent": intent,
                "category": category,
                "sites": sites,
                "metrics": metrics,
                "start_date": start_date,
                "end_date": end_date,
                "comparison_start_date": comparison_start_date,
                "comparison_end_date": comparison_end_date,
            },
            audit=audit,
        )

    return analyze_category_health


def create_metric_catalog_tool(
    service: CategoryHealthService,
    audit_sink: AuditSink,
) -> Callable[..., dict[str, Any]]:
    """Expose application metric discovery as a Deep Agents tool."""

    def list_available_metrics() -> dict[str, Any]:
        """List all supported metric names, IDs, units, and accepted aliases."""

        audit = current_audit.get() or AuditTrail(audit_sink)
        return service.list_metrics(audit=audit)

    return list_available_metrics


def create_category_health_deep_agent(
    *,
    model: str | BaseChatModel,
    service: CategoryHealthService,
    audit_sink: AuditSink,
    harness_profile_key: str | None = None,
):
    """Expose an assembled application service through Deep Agents."""

    profile_key = harness_profile_key or (model if isinstance(model, str) else None)
    if profile_key is None:
        raise ValueError("harness_profile_key is required for a pre-built model client")
    register_harness_profile(
        profile_key,
        HarnessProfile(
            excluded_tools=_BUILT_IN_TOOLS,
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        ),
    )
    analysis_tool = create_analysis_tool(service, audit_sink)
    metric_catalog_tool = create_metric_catalog_tool(service, audit_sink)
    return create_deep_agent(
        model=model,
        tools=[analysis_tool, metric_catalog_tool],
        system_prompt=_SYSTEM_PROMPT,
        name="category-health-analyst",
    )
