"""Interactive OpenAI or MLX CLI using reproducible mock data and local audit."""

import argparse
import json
import os
from pathlib import Path

import duckdb
from category_health.agent.deep_agent import create_category_health_deep_agent
from category_health.agent.session import AnalysisSession
from category_health.catalogs.catalogs import load_metric_catalog, load_site_catalog
from category_health.catalogs.categories import load_category_catalog
from category_health.config import load_local_environment
from category_health.models import build_agent_model, load_model_settings
from category_health.observability import create_audit_sink
from category_health.repositories.duckdb import DuckDbMetricsRepository
from category_health.repositories.mock_data import seed_mock_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chat", action="store_true", help="Keep conversation history for follow-ups"
    )
    parser.add_argument("--provider", choices=("openai", "mlx"))
    parser.add_argument("--model", help="Override the selected provider model.")
    args = parser.parse_args()
    root = Path(__file__).parents[1]
    load_local_environment(root / ".env")
    model_settings = load_model_settings(provider=args.provider, model=args.model)
    if error := model_settings.configuration_error():
        raise SystemExit(error)
    sink = create_audit_sink(root / "audit" / "events.jsonl")
    connection = duckdb.connect(":memory:")
    repository = DuckDbMetricsRepository(connection)
    seed_mock_data(repository)
    agent = create_category_health_deep_agent(
        model=build_agent_model(model_settings),
        harness_profile_key=model_settings.harness_profile_key,
        repository=repository,
        category_catalog=load_category_catalog(root / "data/categories_source.txt"),
        site_catalog=load_site_catalog(root / "data/sites.yaml"),
        metric_catalog=load_metric_catalog(root / "data/metrics.yaml"),
        audit_sink=sink,
    )
    session = AnalysisSession(agent, sink)
    print("MOCK DATA: category 20081; Germany/UK; 2026-08-02 through 2026-09-10.")
    print(f"MODEL: {model_settings.display_name}")
    prompt = os.environ.get(
        "CATEGORY_HEALTH_PROMPT",
        "Show image coverage and misaligned aspects for category 20081 in Germany "
        "for September 9 and September 10, 2026.",
    )
    try:
        while True:
            if args.chat:
                try:
                    prompt = input("\nYou (exit to quit): ").strip()
                except EOFError:
                    break
                if prompt.lower() in {"exit", "quit"}:
                    break
                if not prompt:
                    continue
            start = len(sink.events)
            try:
                answer = session.ask(prompt)
                content = answer.content
                print(
                    content
                    if isinstance(content, str)
                    else "\n".join(
                        block.get("text", "") for block in content if isinstance(block, dict)
                    )
                )
            finally:
                print(f"\nAUDIT TRACE {session.last_trace_id} — {sink.path}")
                for event in sink.events[start:]:
                    print(f"{event.sequence:02d}. {event.step} {event.status.value}")
                    if event.error_message:
                        print(event.error_type, event.error_message)
                    if event.output_object is not None:
                        print(json.dumps(event.output_object, indent=2, default=str))
            if not args.chat:
                break
    finally:
        sink.flush()
        connection.close()


if __name__ == "__main__":
    main()
