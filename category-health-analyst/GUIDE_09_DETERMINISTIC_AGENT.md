# Guide 09 — The Deterministic Agent Core

## Goal

At this stage, the project has a domain model, catalogs, a repository, a structured query specification, and an audit trail.

The next step is to connect those pieces into an agent core that can execute a validated analytical request from beginning to end.

This is intentionally deterministic. It does not yet interpret free-form English. That boundary will be added later through an LLM or another language parser.

## What an agent means in this project

An agent is not simply a chat interface and it is not the same thing as an LLM.

For this project, an agent is a component that:

1. receives a request,
2. validates what the request means,
3. chooses an execution plan,
4. calls the appropriate data capabilities,
5. returns a useful result,
6. records the complete execution trace.

The LLM will eventually help with step 1 and part of step 2. The rest should remain predictable and testable.

## Current execution flow

```text
AnalysisQuery
        |
        v
 Explicit intent routing
        |
        v
   MetricsRepository
        |
        v
  AnalysisResponse
        |
        v
     AuditTrail
```

The analyzer receives an already resolved `AnalysisQuery`. This allows us to test the business behavior without mixing language interpretation, database access, and analytical logic in the same test.

## Why the agent should not execute arbitrary instructions

The agent should not translate a user sentence directly into arbitrary SQL or arbitrary Python code.

Instead, it should choose from known operations and pass validated arguments to known components.

This gives us:

- predictable behavior,
- easier tests,
- safer database access,
- clear audit records,
- explainable failures,
- the ability to add permissions later.

## The role of tools

When we add the language layer, the LLM can select a tool based on the user's request.

For example:

```text
User: Compare image coverage in Germany during the last two weeks.
        |
        v
LLM selects: compare_metric_periods
        |
        v
Validated tool arguments
        |
        v
Deterministic comparison execution
```

The tool name and schema can represent the user's intent. We do not need the user to know internal names such as `period_comparison`.

An internal operation enum may still be useful for routing, authorization, reporting, or audit summaries, but it is an implementation detail. It is not the language understood by the user.

## Current operations

`CategoryHealthAnalyzer.analyze()` routes these normalized intents directly:

| Operation | Purpose |
|---|---|
| `snapshot` | Return the latest relevant value for a category and site |
| `trend` | Return one selected update per day across a date range |
| `compare_periods` | Compare two date ranges |
| `compare_sites` | Compare the same metric across two sites |
| `explain_change` | Describe first-to-last changes between observations |

These operations are deliberately small. Each one has a clear input contract and can be tested independently.

## What is audited

The agent records the major execution stages, including:

- query validation,
- plan creation,
- repository retrieval,
- selected dates and updates,
- output summaries,
- failures and validation errors.

The audit trail is not only for debugging. It lets us answer questions such as:

```text
Which query was interpreted?
Which category and site were resolved?
Which updates were selected?
Why was a particular same-day record used?
What result was returned?
```

## Important time rule

The repository may contain multiple updates for the same category, site, and observed date.

For daily analysis, the agent uses the update with the greatest `last_modified_at` for each day.

This means the answer for a date represents the latest known state for that date, while preserving all source updates in storage for audit and historical investigation.

## What is intentionally not implemented yet

This stage does not yet include:

- free-form English interpretation,
- LLM calls,
- automatic clarification conversations,
- retrieval-augmented explanations,
- arbitrary user-defined calculations,
- production scheduling or monitoring.

Those features depend on this deterministic core. Building them first would make it difficult to identify whether a problem came from language interpretation, planning, storage, or calculation.

## Acceptance criteria

This guide is complete when:

- a valid `AnalysisQuery` reaches the analyzer,
- the correct plan is produced,
- the repository returns the correct records,
- multiple same-day updates are reduced to the latest LMD,
- the result is structured and testable,
- each major step appears in the audit trail,
- invalid requests fail with an explainable error.

## Next guide

The next guide will define the language boundary: how an LLM can choose a tool and produce validated arguments without being allowed to execute arbitrary database logic.
