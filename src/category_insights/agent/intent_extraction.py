"""LLM-based intent extraction: turns a free-text question into a `QueryIntent`.

`category_mention` and `site_mention` come back as the user's raw text,
deliberately unresolved — see `QueryIntent`'s docstring: turning
`category_mention` into a `category_id` is `agent.category_resolution`'s
job, and `site_mention` into a `site_id` is `agent.site_resolution`'s.
`metric_keys` is extracted straight to its final form instead, because the
model is given the closed metric registry to choose from — any key it
invents is dropped, never trusted blindly, the same rule
`site_resolution` applies to LLM-classified site ids.

Date phrases ("last week", "since March 1st") are extracted as the user's
raw text by the same call, then resolved to actual dates by
`date_ranges.resolve_date_range` — a separate, fast-path-first step (see
that module), not something this prompt is asked to compute directly:
date arithmetic is exactly the kind of thing an LLM gets subtly wrong in
ways that are hard to catch downstream.

`history` (recent turns preceding the latest message) exists so a short
follow-up — most importantly, an answer to `agent.graph`'s own
clarifying question ("Which category are you asking about?" -> "laptop
chargers") — is read in context instead of as an isolated, unanswerable
question on its own. Without it, every message is extracted in a vacuum
and a clarification can never actually be resolved: the same question
gets asked again, forever, regardless of what the user replies with.
"""

from datetime import date

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from category_insights.agent.date_ranges import resolve_date_range
from category_insights.domain.models import QueryIntent
from category_insights.domain.ports import ChatModel
from category_insights.metrics import METRICS, METRICS_BY_KEY

ConversationTurn = tuple[str, str]
"""One (role, content) pair, role being `"user"` or `"assistant"`."""


class ExtractedFields(BaseModel):
    """The LLM's raw read of the question, before date phrases are resolved."""

    category_mention: str | None
    site_mention: str | None = None
    metric_keys: list[str] = Field(default_factory=list)
    date_phrase: str | None = None
    comparison_phrase: str | None = None
    wants_explanation: bool = False


def _build_extraction_prompt(question: str, now: date, history: list[ConversationTurn]) -> str:
    metric_list = "\n".join(f"- {metric.key}: {metric.description}" for metric in METRICS)
    history_section = ""
    if history:
        transcript = "\n".join(f"{role}: {content}" for role, content in history)
        history_section = (
            "Conversation so far (oldest first). Read the latest message as a "
            "continuation of it, not a standalone question — most importantly, "
            "if the assistant's last message asked a clarifying question or said "
            "it didn't recognize/couldn't determine something (a category, a "
            "metric, a date), and the latest message supplies that missing or "
            "corrected value, USE THE LATEST MESSAGE'S VALUE. It overrides "
            "anything said or guessed earlier in the conversation, even the "
            "user's own first message — the earlier guess was wrong or "
            "incomplete, that's why the assistant asked again. Never keep an "
            "earlier value the latest message is actively correcting.\n"
            f"{transcript}\n\n"
        )
    return (
        "Extract structured fields describing the user's *overall* intent for "
        "this category-health question. Leave a field null/empty when neither "
        "the latest message nor the conversation context supplies it — never "
        "guess.\n\n"
        f"Today's date is {now.isoformat()}.\n\n"
        f"{history_section}"
        "Fields:\n"
        "- category_mention: the product category being asked about, in the "
        "user's own words, or null.\n"
        "- site_mention: the site/region mentioned (e.g. a country name), or "
        "null.\n"
        "- metric_keys: zero or more of these known metrics, matched by "
        f"meaning (return the key, not the display name):\n{metric_list}\n"
        "- date_phrase: the time period being asked about, in the user's own "
        'words (e.g. "last week", "this month"), or null.\n'
        "- comparison_phrase: a second time period to compare against, in "
        "the user's own words, or null if this isn't a comparison.\n"
        "- wants_explanation: true if the user is asking *why* something "
        "happened, not just what the numbers are.\n\n"
        f"Latest message: {question!r}"
    )


def extract_intent(
    question: str,
    chat_model: ChatModel,
    now: date,
    history: list[ConversationTurn] | None = None,
) -> QueryIntent:
    """Turn the latest message (plus any preceding conversation) into a `QueryIntent`.

    `category_mention` and `site_mention` are returned unresolved (raw
    text) — resolving them is a later graph step. `metric_keys` is
    filtered against the registry so an invented key never reaches a
    downstream tool call. `date_phrase`/`comparison_phrase` are resolved
    via `date_ranges.resolve_date_range`, which may itself make a second,
    separate LLM call for a phrase its fast path doesn't recognize.
    """
    structured_model = chat_model.with_structured_output(ExtractedFields)
    extracted = structured_model.invoke(
        [HumanMessage(content=_build_extraction_prompt(question, now, history or []))]
    )

    valid_metric_keys = [key for key in extracted.metric_keys if key in METRICS_BY_KEY]

    date_range = (
        resolve_date_range(extracted.date_phrase, chat_model, now)
        if extracted.date_phrase
        else None
    )
    comparison_range = (
        resolve_date_range(extracted.comparison_phrase, chat_model, now)
        if extracted.comparison_phrase
        else None
    )

    return QueryIntent(
        category_mention=extracted.category_mention,
        site_mention=extracted.site_mention,
        metric_keys=valid_metric_keys,
        date_range=date_range,
        comparison_range=comparison_range,
        wants_explanation=extracted.wants_explanation,
        raw_question=question,
    )
