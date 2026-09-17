# Guide 10 — The Language and Tool Boundary

## Goal

This guide defines how a natural-language request becomes a safe, structured tool call.

The central rule is:

```text
The LLM may interpret language, but deterministic application code owns execution.
```

## The complete flow

```text
User message
     |
     v
LLM chooses a known tool
     |
     v
Tool arguments are validated
     |
     v
Catalogs resolve names to IDs
     |
     v
Deterministic planner builds the operation
     |
     v
Repository retrieves data
     |
     v
Agent returns result and audit trace
```

The LLM is only one part of this flow. It should not be responsible for database correctness, date selection, LMD handling, or metric calculations.

## Example request

```text
Show image coverage for Armor in Germany for the last seven days.
```

The LLM should select a known tool, such as:

```text
 analyze_category_health
```

and produce structured arguments similar to:

```json
{
  "intent": "trend",
  "category": "Armor",
  "sites": ["Germany"],
  "metrics": ["image coverage"],
  "start_date": "2026-09-03",
  "end_date": "2026-09-09"
}
```

The LLM does not need to know that Germany is site ID `77`, or which category ID represents Armor. Those are catalog responsibilities.

## Tool schemas are contracts

Every tool should have a strict input model. For example:

```python
class GetMetricTrendInput(BaseModel):
    category_name: str
    site_name: str
    metric_name: str
    start_date: date
    end_date: date
```

The schema protects the application from malformed tool calls. It also tells the LLM what information it must provide.

The schema should reject:

- missing required fields,
- invalid dates,
- an end date before a start date,
- unsupported values,
- incorrect data types.

## Natural language is still ambiguous

The LLM cannot always resolve a request completely.

For example, the category map contains duplicate names such as `Armor`. The LLM may correctly identify the category name, but the catalog may find several category IDs with that name.

The correct behavior is not to guess. The system should return a clarification requirement, for example:

```text
I found several categories named "Armor". Please provide the category ID.
```

This is an important separation:

- the LLM extracts what the user said;
- the catalog determines whether that reference is uniquely resolvable;
- the agent asks for clarification when it is not.

## Tool selection is not tool execution

The LLM may select:

```text
compare_metric_periods
```

But it must not:

- invent a new tool,
- write arbitrary SQL,
- bypass the repository,
- silently choose an ambiguous category,
- change stored data,
- claim that missing data exists.

The application checks that the selected tool is registered and that its arguments pass validation before execution begins.

## Where the internal operation fits

We can represent the selected tool internally in either of two ways.

### Option A — tool name is the operation

```text
tool_name = "compare_metric_periods"
```

This is simple and avoids duplicate labels.

### Option B — tool name maps to a normalized operation

```text
compare_metric_periods -> PERIOD_COMPARISON
```

This is useful when several tools share the same business operation or when audit and authorization need stable internal categories.

The user-facing language does not depend on either choice. The important part is that execution uses a registered, validated capability.

## Audit requirements

The audit trail should record at least:

- the original user message,
- the selected tool name,
- the raw tool arguments returned by the LLM,
- validation results,
- resolved category/site/metric IDs,
- the final deterministic plan,
- selected repository records,
- the final answer.

This makes it possible to distinguish between:

```text
The LLM misunderstood the request.
The catalog could not resolve the name.
The request was valid but no data existed.
The repository selected the wrong update.
The answer formatting was incorrect.
```

## Recommended implementation order

We should not begin by connecting a live LLM. First, implement a local tool registry and deterministic argument validation:

1. define tool input models;
2. register the available tools;
3. validate a manually constructed tool call;
4. resolve catalogs;
5. convert the validated call into `AnalyticsQuerySpec`;
6. execute the existing deterministic agent;
7. audit every transition;
8. only then connect an LLM provider.

This gives us a fully testable boundary before introducing model variability.

## Acceptance criteria

This guide is complete when:

- a known tool can be selected by name;
- its arguments are validated;
- category, site, and metric names resolve through catalogs;
- ambiguous names produce a clarification requirement;
- a validated tool call becomes an `AnalyticsQuerySpec`;
- the existing deterministic agent executes it;
- the entire path appears in the audit trail.

## Next guide

The next implementation step is to connect the single `analyze_category_health` tool to the deterministic agent and expose only the fields requested by the user from the complete retrieved rows.
