"""Evidence-based scoring of question interpretation and tool results."""

import re
from decimal import Decimal, InvalidOperation


_UNSUPPORTED_WORDING = {
    r"\bstatistically significant\b": "Claims statistical significance without a statistical test.",
    r"\baverage\b": "Claims an average although period comparison uses latest snapshots.",
    r"\b(?:positive|negative) change\b": "Adds a value judgment not present in the tool result.",
    r"\bnot directly supported\b": "Calls a resolved catalog alias unsupported.",
}


def find_unsupported_answer_claims(answer: str) -> list[str]:
    """Catch known unsupported claims that structured tool scoring cannot see."""

    return [
        message
        for pattern, message in _UNSUPPORTED_WORDING.items()
        if re.search(pattern, answer, flags=re.IGNORECASE)
    ]


def _scenario_turn_id(turn: dict) -> tuple[str, int]:
    return turn["case"], turn["turn"]


def _comparison_labels(reports: list[dict]) -> list[str]:
    """Use provider names when unique and model names for same-provider A/B tests."""

    providers = [report["provider"] for report in reports]
    if len(set(providers)) == len(providers):
        return providers
    models = [report["model"] for report in reports]
    if len(set(models)) != len(models):
        raise ValueError("Comparison reports must have distinct providers or models.")
    return models


def build_provider_comparison(reports: list[dict]) -> dict:
    """Join two provider or model reports by scenario and summarize the A/B test."""

    if len(reports) != 2:
        raise ValueError("Exactly two reports are required for an A/B comparison.")
    labels = _comparison_labels(reports)
    arms = dict(zip(labels, reports, strict=True))
    all_keys = sorted(
        {
            _scenario_turn_id(turn)
            for report in reports
            for turn in report["turns"]
        }
    )
    turns = []
    for case, turn_number in all_keys:
        row = {"case": case, "turn": turn_number, "providers": {}}
        for label, report in arms.items():
            result = next(
                (
                    item
                    for item in report["turns"]
                    if _scenario_turn_id(item) == (case, turn_number)
                ),
                None,
            )
            row["providers"][label] = (
                {
                    "status": result["status"],
                    "duration_seconds": result["duration_seconds"],
                }
                if result
                else {"status": "not_run", "duration_seconds": None}
            )
        statuses = [value["status"] for value in row["providers"].values()]
        row["agreement"] = len(set(statuses)) == 1
        turns.append(row)

    summary = {}
    for label, report in arms.items():
        evaluated = [turn for turn in report["turns"] if turn["status"] != "skipped"]
        passed = sum(turn["status"] == "pass" for turn in evaluated)
        summary[label] = {
            "provider": report["provider"],
            "model": report["model"],
            "counts": report["counts"],
            "pass_rate": passed / len(evaluated) if evaluated else None,
            "duration_seconds": report["duration_seconds"],
            "usage": report.get("usage", {}),
        }
    comparison = {
        "experiment": (
            "provider_comparison"
            if len(set(report["provider"] for report in reports)) == 2
            else "model_comparison"
        ),
        "baseline": labels[0],
        "candidate": labels[1],
        "summary": summary,
        "agreement_rate": (
            sum(row["agreement"] for row in turns) / len(turns) if turns else None
        ),
        "turns": turns,
        "interpretation": (
            "Pass/fail is based on structured audit evidence. Final-answer wording "
            "still requires human review."
        ),
    }
    baseline = summary[labels[0]]
    candidate = summary[labels[1]]
    valid = not baseline["counts"].get("error") and not candidate["counts"].get(
        "error"
    )
    comparison["candidate_vs_baseline"] = {
        "valid": valid,
        "reason": None if valid else "At least one comparison arm had a runtime error.",
        "pass_rate_delta": (
            candidate["pass_rate"] - baseline["pass_rate"] if valid else None
        ),
        "duration_delta_seconds": (
            round(candidate["duration_seconds"] - baseline["duration_seconds"], 4)
            if valid
            else None
        ),
        "speedup": (
            round(baseline["duration_seconds"] / candidate["duration_seconds"], 4)
            if valid and candidate["duration_seconds"]
            else None
        ),
    }
    return comparison


def values_are_equivalent(actual, expected) -> bool:
    """Numeric serialization may differ; booleans and null are never numbers."""
    if isinstance(expected, bool) or expected is None:
        return actual is expected
    if isinstance(actual, bool) or actual is None:
        return False
    try:
        return Decimal(str(actual)) == Decimal(str(expected))
    except InvalidOperation:
        return actual == expected


def evaluate_turn_from_audit(expectation: dict, events: list) -> dict:
    """Select the expected turn type and evaluate its audit evidence."""
    successful_events = [event for event in events if event.status.value == "succeeded"]
    resolved_queries = [
        event.output_object
        for event in successful_events
        if event.step == "resolve_request"
    ]
    analysis_results = [
        event.output_object
        for event in successful_events
        if event.step == "calculate_and_project"
    ]
    clarification_results = [
        event.output_object
        for event in successful_events
        if event.step == "clarification"
    ]
    metric_catalogs = [
        event.output_object
        for event in successful_events
        if event.step == "list_available_metrics"
    ]
    if catalog_expectation := expectation.get("catalog"):
        return _evaluate_metric_catalog_request(
            catalog_expectation,
            metric_catalogs,
            resolved_queries,
            analysis_results,
        )
    if expectation.get("clarification"):
        return _evaluate_clarification_request(
            clarification_results,
            resolved_queries,
            analysis_results,
        )
    return _evaluate_analysis_request(
        expectation,
        events,
        resolved_queries,
        analysis_results,
    )


def _evaluate_metric_catalog_request(
    expectation: dict,
    catalog_outputs: list[dict],
    queries: list[dict],
    analysis_outputs: list[dict],
) -> dict:
    """Verify that discovery returned exactly the expected metric catalog."""

    failures = []
    if queries or analysis_outputs:
        failures.append("Executed an analysis when metric discovery was requested.")
    if not catalog_outputs:
        failures.append("No audited metric catalog result was recorded.")
    for catalog in catalog_outputs:
        actual_ids = [metric["metric_id"] for metric in catalog["metrics"]]
        expected_ids = expectation["metric_ids"]
        if actual_ids != expected_ids:
            failures.append(
                f"Metric catalog mismatch: {actual_ids!r} != {expected_ids!r}"
            )
    return {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "answer_review": "Catalog selection and completeness verified from audit.",
    }


def _evaluate_clarification_request(
    clarifications: list,
    queries: list[dict],
    analysis_outputs: list[dict],
) -> dict:
    """Verify that an ambiguous request stopped before analysis."""

    failures = []
    if queries or analysis_outputs:
        failures.append("Executed an analysis when clarification was required.")
    if not clarifications:
        failures.append("No audited clarification was recorded.")
    return {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "clarification_recorded": bool(clarifications),
        "answer_review": (
            "The audit verifies that execution stopped for clarification; "
            "wording may still be reviewed separately."
        ),
    }


def _evaluate_analysis_request(expectation, events, queries, outputs) -> dict:
    """Verify interpreted scope and deterministic result values."""

    failures = []
    if not queries:
        failures.append("No validated query: the model did not complete the requested tool call.")
    for query in queries:
        for key, expected in expectation["query"].items():
            if query.get(key) != expected:
                failures.append(
                    f"Interpretation mismatch for {key}: {query.get(key)!r} != {expected!r}"
                )
    if not outputs:
        failures.append("No calculated tool result.")
    for output in outputs:
        expected = expectation["result"]
        if output["status"] != expected["status"]:
            failures.append(f"Result status: {output['status']} != {expected['status']}")
        actual_lists = {
            "values": [v["value"] for v in output["values"]],
            "deltas": [c["delta"] for c in output["comparisons"]],
            "units": [c["delta_unit"] for c in output["comparisons"]],
        }
        for key, actual in actual_lists.items():
            wanted = expected[key]
            if len(actual) != len(wanted) or any(
                not values_are_equivalent(actual_value, expected_value)
                for actual_value, expected_value in zip(
                    actual,
                    wanted,
                    strict=False,
                )
            ):
                failures.append(f"Result mismatch for {key}: {actual!r} != {wanted!r}")
    return {
        "status": "fail" if failures else "pass",
        "failures": failures,
        "recovered_errors": sum(e.status.value == "failed" for e in events),
        "answer_review": "Pending: verify wording, units, missing data and unsupported claims.",
    }
