"""Tests for `extract_intent`: LLM field extraction, then date-phrase resolution.

`category_mention`/`site_mention` are expected to pass through unresolved
(see `QueryIntent`'s docstring). `metric_keys` and date phrases each have
their own "don't trust the model blindly" case.
"""

from datetime import date

from category_insights.agent.date_ranges import DateClassification
from category_insights.agent.intent_extraction import (
    ExtractedFields,
    _build_extraction_prompt,
    extract_intent,
)
from tests.conftest import FakeChatModel


def test_extracts_mentions_and_flags_unresolved(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(
            category_mention="running shoes",
            site_mention="Canada",
            metric_keys=["image_count"],
            date_phrase=None,
            comparison_phrase=None,
            wants_explanation=True,
        ),
    )

    intent = extract_intent(
        "Why did image_count drop for running shoes in Canada?", fake_chat_model, fixed_now
    )

    assert intent.category_mention == "running shoes"
    assert intent.site_mention == "Canada"
    assert intent.metric_keys == ["image_count"]
    assert intent.wants_explanation is True
    assert intent.date_range is None
    assert intent.comparison_range is None
    assert intent.raw_question == "Why did image_count drop for running shoes in Canada?"


def test_invented_metric_keys_are_dropped(fixed_now: date, fake_chat_model: FakeChatModel) -> None:
    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(
            category_mention=None,
            metric_keys=["image_count", "totally_made_up_metric"],
        ),
    )

    intent = extract_intent("How's image count doing?", fake_chat_model, fixed_now)

    assert intent.metric_keys == ["image_count"]


def test_recognized_date_phrase_is_resolved_without_a_second_llm_call(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(category_mention="shoes", date_phrase="last week"),
    )

    intent = extract_intent("How did shoes do last week?", fake_chat_model, fixed_now)

    assert intent.date_range is not None
    assert intent.date_range.label == "last week"
    assert fake_chat_model.structured_call_counts == {ExtractedFields: 1}


def test_unrecognized_date_phrase_falls_back_to_the_date_llm(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(category_mention="shoes", date_phrase="the week of the spring sale"),
    )
    fake_chat_model.set_structured_response(
        DateClassification,
        DateClassification(start=date(2026, 5, 4), end=date(2026, 5, 10)),
    )

    intent = extract_intent(
        "How did shoes do the week of the spring sale?", fake_chat_model, fixed_now
    )

    assert intent.date_range is not None
    assert (intent.date_range.start, intent.date_range.end) == (date(2026, 5, 4), date(2026, 5, 10))
    assert fake_chat_model.structured_call_counts[ExtractedFields] == 1
    assert fake_chat_model.structured_call_counts[DateClassification] == 1


def test_comparison_phrase_is_resolved_independently_of_the_primary_range(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    fake_chat_model.set_structured_response(
        ExtractedFields,
        ExtractedFields(
            category_mention="shoes",
            date_phrase="this week",
            comparison_phrase="last week",
        ),
    )

    intent = extract_intent(
        "How does this week compare to last week for shoes?", fake_chat_model, fixed_now
    )

    assert intent.date_range is not None and intent.date_range.label == "this week"
    assert intent.comparison_range is not None and intent.comparison_range.label == "last week"


def test_prompt_has_no_history_section_when_there_is_no_history(fixed_now: date) -> None:
    prompt = _build_extraction_prompt("How is it doing?", fixed_now, [])

    assert "Conversation so far" not in prompt
    assert "Latest message: 'How is it doing?'" in prompt


def test_prompt_includes_prior_turns_so_a_short_reply_reads_in_context(fixed_now: date) -> None:
    # The bug this guards against: without history, a one-word reply to the
    # agent's own clarifying question ("laptop chargers") is extracted with
    # no idea what it's answering, so the same clarification gets asked
    # again no matter what the user replies with.
    history = [
        ("user", "how are things going"),
        ("assistant", "Which category are you asking about?"),
    ]

    prompt = _build_extraction_prompt("laptop chargers", fixed_now, history)

    assert "Conversation so far" in prompt
    assert "user: how are things going" in prompt
    assert "assistant: Which category are you asking about?" in prompt
    assert "Latest message: 'laptop chargers'" in prompt


def test_extract_intent_accepts_history_without_erroring(
    fixed_now: date, fake_chat_model: FakeChatModel
) -> None:
    fake_chat_model.set_structured_response(
        ExtractedFields, ExtractedFields(category_mention="laptop chargers")
    )
    history = [("assistant", "Which category are you asking about?")]

    intent = extract_intent("laptop chargers", fake_chat_model, fixed_now, history=history)

    assert intent.category_mention == "laptop chargers"
