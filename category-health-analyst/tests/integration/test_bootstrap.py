from pathlib import Path

from category_health.bootstrap import create_demo_runtime


PROJECT_ROOT = Path(__file__).parents[2]


def test_demo_runtime_wires_the_deterministic_application(tmp_path: Path) -> None:
    runtime = create_demo_runtime(
        PROJECT_ROOT,
        audit_path=tmp_path / "events.jsonl",
        audit_environment={},
    )
    try:
        response = runtime.service.analyze(
            {
                "intent": "trend",
                "category": "Antiques",
                "sites": ["Germany"],
                "metrics": ["image coverage"],
                "start_date": "2026-09-09",
                "end_date": "2026-09-10",
            }
        )
    finally:
        runtime.close()

    assert response["status"] == "ok"
    assert [value["value"] for value in response["values"]] == [
        "72.0000",
        "64.0000",
    ]
    assert response["comparisons"][0]["delta"] == "-8.0000"
