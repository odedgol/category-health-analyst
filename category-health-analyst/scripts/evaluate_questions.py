"""Evaluate fixtures, one live model, or a controlled two-arm experiment."""

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import yaml
from category_health.agent.deep_agent import create_category_health_deep_agent
from category_health.agent.session import AnalysisSession
from category_health.bootstrap import create_demo_runtime
from category_health.config import load_local_environment
from category_health.evaluation import (
    build_provider_comparison,
    evaluate_turn_from_audit,
    find_unsupported_answer_claims,
)
from category_health.model_provider import (
    ModelSettings,
    build_agent_model,
    load_model_settings,
    local_server_error,
)


def _message_usage(messages: list) -> dict[str, int]:
    """Sum usage from every model call in one agent turn, including tool selection."""

    keys = ("input_tokens", "output_tokens", "total_tokens")
    return {
        key: sum(
            (getattr(message, "usage_metadata", None) or {}).get(key, 0)
            for message in messages
        )
        for key in keys
    }


def run_suite(
    *,
    root: Path,
    suite: dict,
    cases: list[dict],
    run_dir: Path,
    settings: ModelSettings | None,
) -> dict:
    """Run one isolated provider against the selected cases."""

    live = settings is not None
    runtime = create_demo_runtime(
        root,
        audit_path=run_dir / "events.jsonl",
        audit_environment=None if live else {},
    )
    sink = runtime.audit_sink

    def analyze(**arguments):
        return runtime.service.analyze_arguments(arguments)

    graph = None
    if live:
        graph = create_category_health_deep_agent(
            model=build_agent_model(settings),
            harness_profile_key=settings.harness_profile_key,
            service=runtime.service,
            audit_sink=sink,
        )
    report = {
        "mode": "live" if live else "offline_fixture_check",
        "provider": settings.provider.value if settings else "offline",
        "model": settings.model if settings else None,
        "base_url": settings.base_url if settings else None,
        "today": suite["today"],
        "turns": [],
        "answer_review": (
            "Known unsupported wording is checked automatically; remaining wording "
            "requires human review."
        ),
    }
    started = perf_counter()

    def save() -> None:
        report["counts"] = dict(Counter(turn["status"] for turn in report["turns"]))
        report["usage"] = {
            key: sum(
                (turn.get("usage") or {}).get(key, 0) for turn in report["turns"]
            )
            for key in ("input_tokens", "output_tokens", "total_tokens")
        }
        report["duration_seconds"] = round(perf_counter() - started, 4)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )

    try:
        for case in cases:
            session = AnalysisSession(graph, sink, today=date.fromisoformat(suite["today"]))
            for index, turn in enumerate(case["turns"], 1):
                event_start = len(sink.events)
                turn_started = perf_counter()
                item = {
                    "case": case["id"],
                    "turn": index,
                    "question": turn["question"],
                    "expected": turn,
                }
                try:
                    if live:
                        message_start = len(session.messages)
                        answer = session.ask(turn["question"])
                        item["answer"] = answer.content
                        item["usage"] = _message_usage(session.messages[message_start:])
                        item["trace_id"] = str(session.last_trace_id)
                    elif turn.get("clarification"):
                        item.update(status="skipped", reason="Requires language interpretation.")
                    elif turn.get("catalog"):
                        result = runtime.service.list_metrics()
                        item["trace_id"] = result["trace_id"]
                    else:
                        query = turn["query"]
                        scope = query["date_range"] or {}
                        comparison = query["comparison_range"] or {}
                        result = analyze(
                            intent=query["intent"],
                            category=str(query["category_id"]),
                            sites=[str(site) for site in query["site_ids"]],
                            metrics=query["metric_ids"],
                            start_date=scope.get("start"),
                            end_date=scope.get("end"),
                            comparison_start_date=comparison.get("start"),
                            comparison_end_date=comparison.get("end"),
                        )
                        item["trace_id"] = result["trace_id"]
                    if item.get("status") != "skipped":
                        item.update(
                            evaluate_turn_from_audit(turn, sink.events[event_start:])
                        )
                        if live and isinstance(item.get("answer"), str):
                            wording_failures = find_unsupported_answer_claims(
                                item["answer"]
                            )
                            item["wording_failures"] = wording_failures
                            if wording_failures and item["status"] == "pass":
                                item["status"] = "needs_review"
                except Exception as error:
                    item.update(status="error", error_type=type(error).__name__)
                    if live:
                        item["trace_id"] = str(session.last_trace_id)
                item["duration_seconds"] = round(perf_counter() - turn_started, 4)
                report["turns"].append(item)
                save()
                print(
                    f"{report['provider']} / {case['id']} / turn {index}: "
                    f"{item['status']} ({item['duration_seconds']:.2f}s)"
                )
                if item["status"] == "error":
                    break
    finally:
        save()
        runtime.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call the selected provider.")
    parser.add_argument(
        "--compare", action="store_true", help="Run the same live suite against OpenAI and MLX."
    )
    parser.add_argument(
        "--compare-reports",
        nargs=2,
        metavar=("BASELINE_REPORT", "CANDIDATE_REPORT"),
        help="Compare any two existing provider/model reports without new model calls.",
    )
    parser.add_argument("--provider", choices=("openai", "mlx"))
    parser.add_argument("--model", help="Override the selected provider's model for this run.")
    parser.add_argument("--case", help="Run only this case ID.")
    parser.add_argument("--list", action="store_true", help="List cases without running.")
    args = parser.parse_args()
    if args.compare and (args.provider or args.model or args.compare_reports):
        parser.error("--compare uses configured OpenAI and MLX models; omit --provider/--model.")
    if args.compare_reports and (
        args.live or args.provider or args.model or args.case or args.list
    ):
        parser.error("--compare-reports cannot be combined with live/model/case options.")

    root = Path(__file__).parents[1]
    load_local_environment(root / ".env")
    suite = yaml.safe_load((root / "evals/questions.yaml").read_text(encoding="utf-8"))
    cases = [case for case in suite["cases"] if not args.case or case["id"] == args.case]
    if not cases:
        parser.error("Unknown case ID.")
    if args.list:
        for case in cases:
            print(case["id"], f"({len(case['turns'])} turns)")
        return 0

    evaluation_root = root / "audit" / "evaluations" / str(uuid4())
    if args.compare_reports:
        reports = [
            json.loads(Path(report_path).read_text(encoding="utf-8"))
            for report_path in args.compare_reports
        ]
        try:
            comparison = build_provider_comparison(reports)
        except ValueError as error:
            parser.error(str(error))
        evaluation_root.mkdir(parents=True, exist_ok=True)
        comparison_path = evaluation_root / "comparison.json"
        comparison_path.write_text(
            json.dumps(comparison, indent=2, default=str), encoding="utf-8"
        )
        print(f"Comparison: {comparison_path}")
        result = comparison["candidate_vs_baseline"]
        return int(not result["valid"] or (result["pass_rate_delta"] or 0) < 0)
    if args.compare:
        settings_list = [
            load_model_settings(provider="openai"),
            load_model_settings(provider="mlx"),
        ]
        for settings in settings_list:
            if error := settings.configuration_error():
                parser.error(error)
            if error := local_server_error(settings):
                parser.error(error)
        reports = [
            run_suite(
                root=root,
                suite=suite,
                cases=cases,
                run_dir=evaluation_root / settings.provider.value,
                settings=settings,
            )
            for settings in settings_list
        ]
        comparison = build_provider_comparison(reports)
        comparison_path = evaluation_root / "comparison.json"
        comparison_path.write_text(
            json.dumps(comparison, indent=2, default=str), encoding="utf-8"
        )
        print(f"Comparison: {comparison_path}")
        return int(
            any(
                turn["status"] not in {"pass", "skipped"}
                for report in reports
                for turn in report["turns"]
            )
        )

    live = args.live or bool(args.provider or args.model)
    settings = load_model_settings(provider=args.provider, model=args.model) if live else None
    if settings and (error := settings.configuration_error()):
        parser.error(error)
    if settings and (error := local_server_error(settings)):
        parser.error(error)
    report = run_suite(
        root=root,
        suite=suite,
        cases=cases,
        run_dir=evaluation_root,
        settings=settings,
    )
    print(f"Mode: {report['mode']}; counts: {report['counts']}")
    print(f"Report: {evaluation_root / 'report.json'}")
    print("Structured evidence evaluation complete; wording is not automatically graded.")
    return int(any(turn["status"] not in {"pass", "skipped"} for turn in report["turns"]))


if __name__ == "__main__":
    raise SystemExit(main())
