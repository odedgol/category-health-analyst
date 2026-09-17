# Guide 12 — Deep Agents as the Outer Layer

## Goal

Deep Agents is now used as the LLM orchestration layer. It does not own the business logic.

```text
Deep Agent
    language understanding and tool selection
        |                         |
        v                         v
analyze_category_health    list_available_metrics
        |                         |
        v                         v
analytics core             static MetricCatalog
repository + calculations  names + units + aliases
        |                         |
        +------------ audit ------+
```

## Why this separation matters

Deep Agents can plan and call tools, but it does not know what an eBay category metric means. Our code remains responsible for:

- resolving category and site references;
- selecting the latest LMD per observed day;
- retrieving complete metric rows;
- calculating trends and comparisons;
- returning only requested fields;
- recording business-level audit events.

## Security boundary

Deep Agents includes filesystem, shell, and subagent capabilities by default. This project does not need those capabilities.

The adapter registers a harness profile that excludes those built-in tools. It
exposes only two closed domain capabilities: analysis and metric discovery.

This follows the framework's security principle: enforce boundaries in the available tools, not by asking the model to police itself.

## What the domain tools do

The single analysis tool, `analyze_category_health`:

1. validates the model-generated arguments;
2. resolves catalogs;
3. creates an `AnalyticsQuerySpec`;
4. runs the deterministic agent;
5. projects the complete result into the requested output;
6. returns JSON-safe data.

The Deep Agent sees the final response, while the audit sink retains the detailed trace.

`list_available_metrics` is intentionally separate. It reads the existing static
`MetricCatalog` and returns every metric ID, display name, unit and accepted alias.
It requires no category, site, date or database query. This lets the model answer
catalog questions without inventing names or forcing an artificial analysis scope.

## Acceptance criteria

This guide is complete when:

- Deep Agents can be created with a model identifier;
- only the two closed domain tools are exposed;
- the domain tool runs the existing deterministic core;
- metric discovery returns the complete static catalog and is audited;
- complete rows remain available before projection;
- the returned value is JSON-safe;
- domain audit events remain intact.
