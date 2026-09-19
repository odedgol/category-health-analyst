from types import SimpleNamespace

from category_health.evaluation import evaluate_turn_from_audit, values_are_equivalent


def event(step, output):
    return SimpleNamespace(
        step=step, output_object=output, status=SimpleNamespace(value="succeeded")
    )


def expectation():
    return {
        "query": {"site_ids": [77]},
        "result": {
            "status": "ok",
            "values": ["72", "64"],
            "deltas": ["-8"],
            "units": ["percentage_points"],
        },
    }


def events():
    return [
        event("resolve_request", {"site_ids": [77]}),
        event(
            "analysis_response",
            {
                "status": "ok",
                "values": [{"value": "72.0000"}, {"value": "64.0000"}],
                "comparisons": [{"delta": "-8.0000", "delta_unit": "percentage_points"}],
            },
        ),
    ]


def test_numerical_equivalence_does_not_confuse_booleans():
    assert values_are_equivalent("72.0000", 72)
    assert not values_are_equivalent(True, 1)
    assert not values_are_equivalent(0, False)
    assert not values_are_equivalent(None, 0)


def test_correct_result_passes_but_answer_still_requires_review():
    score = evaluate_turn_from_audit(expectation(), events())
    assert score["status"] == "pass"
    assert "Pending" in score["answer_review"]


def test_correct_last_call_does_not_hide_wrong_scope():
    trace = [event("resolve_request", {"site_ids": [3]}), *events()]
    assert evaluate_turn_from_audit(expectation(), trace)["status"] == "fail"


def test_duplicate_comparisons_fail():
    trace = events()
    output = trace[-1].output_object
    output["comparisons"] *= 2
    assert evaluate_turn_from_audit(expectation(), trace)["status"] == "fail"


def test_missing_tool_output_fails_even_if_model_could_say_correct_number():
    assert evaluate_turn_from_audit(expectation(), [])["status"] == "fail"


def test_audited_clarification_passes_and_rejects_execution():
    clarification = event("clarification", {"unresolved_fields": ["category"]})
    assert evaluate_turn_from_audit({"clarification": True}, [clarification])["status"] == "pass"
    assert evaluate_turn_from_audit({"clarification": True}, [])["status"] == "fail"
    assert evaluate_turn_from_audit({"clarification": True}, events())["status"] == "fail"


def test_metric_catalog_requires_complete_audited_listing_without_analysis():
    expected = {"catalog": {"metric_ids": ["image_count", "has_title"]}}
    listing = event(
        "list_available_metrics",
        {"metrics": [{"metric_id": "image_count"}, {"metric_id": "has_title"}]},
    )

    assert evaluate_turn_from_audit(expected, [listing])["status"] == "pass"
    assert evaluate_turn_from_audit(expected, [listing, *events()])["status"] == "fail"
    assert evaluate_turn_from_audit(expected, [])["status"] == "fail"
