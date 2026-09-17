# Guide 11 — Complete Retrieval, Focused Output

## Goal

The repository returns complete aggregate rows because those rows are the source facts needed for analysis and auditing.

The user usually does not need every field in every answer. The output layer projects the complete result into only the requested metrics while preserving site, period, date, and LMD context.

## Two different representations

```text
Complete stored row
    category + site + date + LMD + all metrics
             |
             v
      analytical calculation
             |
             v
Focused response
    selected metric + context needed to explain it
```

The complete row remains available inside the agent result and audit trail. The focused response is the presentation contract.

## Why retrieval and presentation are separate

If the database query selected only one field too early, later analysis could not answer a follow-up question such as:

```text
The image coverage decreased. Did misaligned aspects increase too?
```

By retrieving the complete row first, the calculation layer has all stored facts available. The output layer decides what to expose for the current request.

## What the output contains

Each exposed value includes:

- site ID;
- semantic period, such as `current` or `comparison`;
- observed date;
- last-modified timestamp;
- metric ID;
- metric value.

The LMD is included because two values from the same observed date can come from different updates.

## Important boundary

The output layer does not redefine business metrics. It selects values that were already stored and exposes calculations produced by the analytical layer.

For example:

- `image_coverage_percentage` comes from the stored aggregate row;
- `image_count` comes from the stored aggregate row;
- a change between two coverage values is calculated by the analyst;
- the output layer formats or selects those results.

For a trend request, consecutive numeric values are compared in deterministic Python code. The response includes the previous value, current value, and delta so the LLM can explain the result without performing the arithmetic itself.

## Acceptance criteria

This guide is complete when:

- complete rows are available internally;
- only requested metrics appear in the response;
- site, date, period, and LMD context are preserved;
- unknown metric IDs fail clearly;
- the full internal result remains available for audit.
