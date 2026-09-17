"""Interactive OpenAI or MLX CLI using reproducible mock data and local audit."""

import argparse
import json
import os
from pathlib import Path

from category_health.bootstrap import create_demo_conversation_runtime
from category_health.config import load_local_environment
from category_health.model_provider import load_model_settings


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
    runtime = create_demo_conversation_runtime(
        root,
        audit_path=root / "audit" / "events.jsonl",
        source="agent",
        model_settings=model_settings,
    )
    sink = runtime.audit_sink
    session = runtime.analysis_session
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
        runtime.close()


if __name__ == "__main__":
    main()
