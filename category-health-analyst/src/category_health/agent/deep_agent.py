"""Assemble Deep Agents around the category-health tools."""

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_core.language_models.chat_models import BaseChatModel

from category_health.agent.prompt import CATEGORY_HEALTH_SYSTEM_PROMPT
from category_health.agent.tools import (
    create_analysis_tool,
    create_metric_catalog_tool,
)
from category_health.tool_adapter import CategoryHealthToolAdapter

_BUILT_IN_TOOLS = frozenset(
    {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "task",
    }
)


def create_category_health_deep_agent(
    *,
    model: str | BaseChatModel,
    tool_adapter: CategoryHealthToolAdapter,
    harness_profile_key: str | None = None,
):
    """Build the language interpreter around two domain tools."""

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
    return create_deep_agent(
        model=model,
        tools=[
            create_analysis_tool(tool_adapter),
            create_metric_catalog_tool(tool_adapter),
        ],
        system_prompt=CATEGORY_HEALTH_SYSTEM_PROMPT,
        name="category-health-analyst",
    )


# Keep imports stable for callers that used the original module as the tool factory.
__all__ = [
    "create_analysis_tool",
    "create_category_health_deep_agent",
    "create_metric_catalog_tool",
]
