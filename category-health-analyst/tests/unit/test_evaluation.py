from types import SimpleNamespace

from category_health.evaluation import same_value, score_turn


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
        event("build_query", {"site_ids": [77]}),
        event(
            "calculate_and_project",
            {
                "status": "ok",
                "values": [{"value": "72.0000"}, {"value": "64.0000"}],
                "comparisons": [{"delta": "-8.0000", "delta_unit": "percentage_points"}],
            },
        ),
    ]


def test_numerical_equivalence_does_not_confuse_booleans():
    assert same_value("72.0000", 72)
    assert not same_value(True, 1)
    assert not same_value(0, False)
    assert not same_value(None, 0)


def test_correct_result_passes_but_answer_still_requires_review():
    score = score_turn(expectation(), events())
    assert score["status"] == "pass"
    assert "Pending" in score["answer_review"]


def test_correct_last_call_does_not_hide_wrong_scope():
    trace = [event("build_query", {"site_ids": [3]}), *events()]
    assert score_turn(expectation(), trace)["status"] == "fail"


def test_duplicate_comparisons_fail():
    trace = events()
    output = trace[-1].output_object
    output["comparisons"] *= 2
    assert score_turn(expectation(), trace)["status"] == "fail"


def test_missing_tool_output_fails_even_if_model_could_say_correct_number():
    assert score_turn(expectation(), [])["status"] == "fail"


def test_audited_clarification_passes_and_rejects_execution():
    clarification = event("clarification", {"unresolved_fields": ["category"]})
    assert score_turn({"clarification": True}, [clarification])["status"] == "pass"
    assert score_turn({"clarification": True}, [])["status"] == "fail"
    assert score_turn({"clarification": True}, events())["status"] == "fail"


def test_metric_catalog_requires_complete_audited_listing_without_analysis():
    expected = {"catalog": {"metric_ids": ["image_count", "has_title"]}}
    listing = event(
        "list_available_metrics",
        {"metrics": [{"metric_id": "image_count"}, {"metric_id": "has_title"}]},
    )

    assert score_turn(expected, [listing])["status"] == "pass"
    assert score_turn(expected, [listing, *events()])["status"] == "fail"
    assert score_turn(expected, [])["status"] == "fail"
