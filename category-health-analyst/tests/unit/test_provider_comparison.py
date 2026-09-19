from category_health.evaluation import (
    build_provider_comparison,
    find_unsupported_answer_claims,
)


def report(provider, status, duration, model=None):
    return {
        "provider": provider,
        "model": model or f"{provider}-model",
        "counts": {status: 1},
        "duration_seconds": duration,
        "turns": [
            {
                "case": "coverage_trend",
                "turn": 1,
                "status": status,
                "duration_seconds": duration,
            }
        ],
    }


def test_provider_comparison_reports_quality_latency_and_disagreement() -> None:
    comparison = build_provider_comparison(
        [report("openai", "pass", 1.2), report("mlx", "fail", 0.4)]
    )

    assert comparison["summary"]["openai"]["pass_rate"] == 1
    assert comparison["summary"]["mlx"]["pass_rate"] == 0
    assert comparison["summary"]["mlx"]["duration_seconds"] == 0.4
    assert comparison["agreement_rate"] == 0
    assert comparison["turns"][0]["agreement"] is False
    assert comparison["candidate_vs_baseline"]["valid"] is True
    assert comparison["candidate_vs_baseline"]["pass_rate_delta"] == -1
    assert comparison["candidate_vs_baseline"]["speedup"] == 3


def test_provider_error_invalidates_quality_and_speed_comparison() -> None:
    openai = report("openai", "error", 0.2)
    mlx = report("mlx", "pass", 2.0)

    comparison = build_provider_comparison([openai, mlx])

    assert comparison["candidate_vs_baseline"]["valid"] is False
    assert comparison["candidate_vs_baseline"]["pass_rate_delta"] is None
    assert comparison["candidate_vs_baseline"]["speedup"] is None


def test_same_provider_models_are_compared_by_model_name() -> None:
    baseline = report("openai", "pass", 1.2, model="gpt-5.5")
    candidate = report("openai", "pass", 0.6, model="gpt-5.4-mini")

    comparison = build_provider_comparison([baseline, candidate])

    assert comparison["experiment"] == "model_comparison"
    assert comparison["baseline"] == "gpt-5.5"
    assert comparison["candidate"] == "gpt-5.4-mini"
    assert comparison["summary"]["gpt-5.4-mini"]["provider"] == "openai"
    assert comparison["candidate_vs_baseline"]["pass_rate_delta"] == 0
    assert comparison["candidate_vs_baseline"]["speedup"] == 2


def test_answer_review_catches_unsupported_analytical_claims() -> None:
    issues = find_unsupported_answer_claims(
        "The average fell and this was statistically significant, a positive change."
    )

    assert len(issues) == 3
    assert find_unsupported_answer_claims(
        "Coverage decreased by 8 percentage points."
    ) == []
