"""Run one real analysis request and print its business-audit flow."""

import json
from pathlib import Path
from uuid import UUID

from category_health.application.requests import AnalysisRequest
from category_health.bootstrap import create_demo_runtime


def main() -> None:
    project_root = Path(__file__).parents[1]
    runtime = create_demo_runtime(
        project_root,
        audit_path=project_root / "audit" / "demo" / "events.jsonl",
        audit_environment={},
    )
    try:
        request = AnalysisRequest(
            intent="trend",
            category="Antiques",
            sites=("Germany",),
            metrics=("image coverage",),
            start_date="2026-09-09",
            end_date="2026-09-10",
        )
        response = runtime.tool_adapter.analyze(request.model_dump(mode="json"))

        print(json.dumps(response, indent=2))
        print("\nAUDIT FLOW")
        for event in runtime.audit_sink.for_trace(UUID(response["trace_id"])):
            if event.status.value != "succeeded":
                continue
            summary = json.dumps(event.output_summary, default=str)
            print(f"{event.step:<24} {summary}")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
