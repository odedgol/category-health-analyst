"""The LangGraph pipeline: ties every agent step into one graph.

    extract_intent -> resolve_site -> resolve_category -+-> clarify -> END
                                                          |
                                                          +-> fetch_data -+-> format_answer -> END
                                                                          |
                                                                          +-> retrieve_notes -+

`resolve_category` is the one branch point before any tool call: a
missing mention, an unrecognized one, or a match below `"high"`
confidence all route to `clarify` instead of guessing — see
`agent.category_resolution`'s docstring for why a non-`"high"` match is a
legitimate outcome, not a bug. `retrieve_notes` runs when
`intent.wants_explanation` is set, *or* when a computed comparison moved
by more than `settings.category_insights_unexpected_delta_threshold`
percentage points — a swing that large is worth explaining even if
nobody explicitly asked "why" — so a plain, unremarkable numbers question
never pays for a retrieval call it didn't need.

Every node takes and returns a plain dict (LangGraph merges returned keys
into `AgentState`) so each step stays independently testable — the tests
in `test_graph.py` call node functions directly far more often than they
compile and run the whole graph.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from category_insights.agent.answer_formatting import (
    format_answer,
    format_metric_series,
    format_notes,
    format_period_comparison,
    format_snapshot,
)
from category_insights.agent.category_resolution import CategoryResolutionHandler, resolve_category
from category_insights.agent.intent_extraction import ConversationTurn, extract_intent
from category_insights.agent.site_resolution import resolve_site_with_learning
from category_insights.bootstrap import AdapterBundle
from category_insights.domain.models import (
    CategoryMatch,
    CategorySnapshot,
    MetricPoint,
    NoteChunk,
    PeriodComparison,
    QueryIntent,
)
from category_insights.domain.ports import MetricDataUnavailableError
from category_insights.mcp_server.tools import (
    CompareMetricPeriodsCommand,
    CompareMetricPeriodsInput,
    GetCategorySnapshotCommand,
    GetCategorySnapshotInput,
    GetMetricHistoryCommand,
    GetMetricHistoryInput,
    SearchCategoryNotesCommand,
    SearchCategoryNotesInput,
)
from category_insights.metrics import METRICS
from category_insights.settings import Settings


@dataclass(frozen=True)
class AnswerResult:
    """The text answer plus whichever structured data backed it.

    Exactly one of `metric_series`/`comparisons`/`snapshot` is populated
    for a fetched answer (matching `fetch_data_node`'s three branches);
    all are empty/`None` for a clarification. Kept separate from the
    text so a caller that wants to chart the numbers (the Streamlit UI)
    doesn't have to parse them back out of `text` — `format_answer` and a
    chart render the same underlying data two different ways, not one
    derived from the other.
    """

    text: str
    metric_series: dict[str, list[MetricPoint]] = field(default_factory=dict)
    comparisons: list[PeriodComparison] = field(default_factory=list)
    snapshot: CategorySnapshot | None = None


class AgentState(TypedDict, total=False):
    """Accumulates as the graph runs. Every field is optional — only set once its node has run."""

    raw_question: str
    now: date
    history: list[ConversationTurn]
    intent: QueryIntent
    site_id: int
    category_match: CategoryMatch | None
    clarification: str | None
    data_lines: list[str]
    metric_series: dict[str, list[MetricPoint]]
    comparisons: list[PeriodComparison]
    snapshot: CategorySnapshot | None
    unexpected_delta: bool
    notes: list[NoteChunk]
    answer: str


def _default_metric_keys(intent: QueryIntent) -> list[str]:
    return intent.metric_keys or [metric.key for metric in METRICS]


def build_graph(
    adapters: AdapterBundle, category_handlers: list[CategoryResolutionHandler], settings: Settings
) -> StateGraph:
    """Wire every agent step into a compiled graph, closing over `adapters`.

    `category_handlers` is passed separately (rather than added to
    `AdapterBundle`) because it's a chain of plain objects, not an
    adapter with external state — building it is `bootstrap`'s call to
    make, but it doesn't belong in the same bundle as real DB/Chroma/LLM
    connections.
    """
    get_metric_history_command = GetMetricHistoryCommand(adapters.repository)
    compare_metric_periods_command = CompareMetricPeriodsCommand(adapters.repository)
    get_category_snapshot_command = GetCategorySnapshotCommand(adapters.repository)
    search_category_notes_command = SearchCategoryNotesCommand(adapters.note_retriever)

    def extract_intent_node(state: AgentState) -> dict:
        intent = extract_intent(
            state["raw_question"],
            adapters.chat_model,
            state["now"],
            history=state.get("history"),
        )
        return {"intent": intent}

    def resolve_site_node(state: AgentState) -> dict:
        site_id = resolve_site_with_learning(
            state["intent"].site_mention, adapters.chat_model, adapters.learned_site_aliases
        )
        return {"site_id": site_id}

    def resolve_category_node(state: AgentState) -> dict:
        intent = state["intent"]
        if intent.category_mention is None:
            return {"clarification": "Which category are you asking about?"}

        categories = adapters.repository.list_categories()
        match = resolve_category(intent.category_mention, categories, category_handlers)

        if match is None or match.confidence == "low":
            # "low" is the semantic handler's honest floor, not a guess worth
            # naming — at that similarity, surfacing it as "did you mean X?"
            # would read as more confident than the match actually is.
            return {
                "clarification": (
                    f"I don't recognize a category called {intent.category_mention!r}. "
                    "Could you rephrase, or use the category's exact name?"
                )
            }
        if match.confidence == "medium":
            return {
                "category_match": match,
                "clarification": (
                    f"Did you mean {match.name!r}? I'm not fully sure — please confirm or rephrase."
                ),
            }
        return {"category_match": match}

    def route_after_category(state: AgentState) -> Literal["clarify", "fetch_data"]:
        return "clarify" if state.get("clarification") else "fetch_data"

    def clarify_node(state: AgentState) -> dict:
        return {"answer": state["clarification"]}

    def fetch_data_node(state: AgentState) -> dict:
        intent = state["intent"]
        category_id = state["category_match"].category_id
        site_id = state["site_id"]
        metric_keys = _default_metric_keys(intent)
        data_lines: list[str] = []
        unexpected_delta = False

        if intent.date_range and intent.comparison_range:
            comparisons: list[PeriodComparison] = []
            for metric_key in metric_keys:
                try:
                    output = compare_metric_periods_command.execute(
                        CompareMetricPeriodsInput(
                            category_id=category_id,
                            site_id=site_id,
                            metric_key=metric_key,
                            period_a_start=intent.comparison_range.start,
                            period_a_end=intent.comparison_range.end,
                            period_b_start=intent.date_range.start,
                            period_b_end=intent.date_range.end,
                        )
                    )
                    data_lines.append(format_period_comparison(output.comparison))
                    comparisons.append(output.comparison)
                    # Percentage-point delta, not the raw fraction — matches how
                    # `category_insights_unexpected_delta_threshold` is documented
                    # in `.env.example`.
                    delta_points = abs(output.comparison.pct_delta) * 100
                    if delta_points >= settings.category_insights_unexpected_delta_threshold:
                        unexpected_delta = True
                except MetricDataUnavailableError as error:
                    data_lines.append(str(error))
            return {
                "data_lines": data_lines,
                "comparisons": comparisons,
                "unexpected_delta": unexpected_delta,
            }

        if intent.date_range or intent.comparison_range:
            date_range = intent.date_range or intent.comparison_range
            assert date_range is not None  # one of the two, checked above
            metric_series: dict[str, list[MetricPoint]] = {}
            for metric_key in metric_keys:
                output = get_metric_history_command.execute(
                    GetMetricHistoryInput(
                        category_id=category_id,
                        site_id=site_id,
                        metric_key=metric_key,
                        start_date=date_range.start,
                        end_date=date_range.end,
                    )
                )
                data_lines.append(format_metric_series(metric_key, output.points))
                metric_series[metric_key] = output.points
            return {"data_lines": data_lines, "metric_series": metric_series}

        output = get_category_snapshot_command.execute(
            GetCategorySnapshotInput(category_id=category_id, site_id=site_id)
        )
        data_lines.append(format_snapshot(output.snapshot))
        return {"data_lines": data_lines, "snapshot": output.snapshot}

    def route_after_fetch(state: AgentState) -> Literal["retrieve_notes", "format_answer"]:
        # Notes are retrieved either because the user asked "why", or because a
        # comparison moved by more than `category_insights_unexpected_delta_threshold`
        # — a swing that big is worth explaining even if nobody asked.
        wants_notes = state["intent"].wants_explanation or state.get("unexpected_delta", False)
        return "retrieve_notes" if wants_notes else "format_answer"

    def retrieve_notes_node(state: AgentState) -> dict:
        output = search_category_notes_command.execute(
            SearchCategoryNotesInput(
                category_id=state["category_match"].category_id, query=state["raw_question"]
            )
        )
        return {"notes": output.notes}

    def format_answer_node(state: AgentState) -> dict:
        note_section = format_notes(state.get("notes", []))
        answer = format_answer(state["data_lines"], note_section)
        return {"answer": answer}

    graph = StateGraph(AgentState)
    graph.add_node("extract_intent", extract_intent_node)
    graph.add_node("resolve_site", resolve_site_node)
    graph.add_node("resolve_category", resolve_category_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("fetch_data", fetch_data_node)
    graph.add_node("retrieve_notes", retrieve_notes_node)
    graph.add_node("format_answer", format_answer_node)

    graph.set_entry_point("extract_intent")
    graph.add_edge("extract_intent", "resolve_site")
    graph.add_edge("resolve_site", "resolve_category")
    graph.add_conditional_edges(
        "resolve_category",
        route_after_category,
        {"clarify": "clarify", "fetch_data": "fetch_data"},
    )
    graph.add_edge("clarify", END)
    graph.add_conditional_edges(
        "fetch_data",
        route_after_fetch,
        {"retrieve_notes": "retrieve_notes", "format_answer": "format_answer"},
    )
    graph.add_edge("retrieve_notes", "format_answer")
    graph.add_edge("format_answer", END)

    return graph.compile()


def answer_question(
    question: str,
    adapters: AdapterBundle,
    category_handlers: list[CategoryResolutionHandler],
    settings: Settings | None = None,
    now: date | None = None,
    history: list[ConversationTurn] | None = None,
) -> AnswerResult:
    """Run the full graph for one message and return its answer, text plus structured data.

    `history` is the conversation's prior turns (oldest first), passed
    straight through to `intent_extraction.extract_intent` — without it,
    a short reply to the graph's own clarifying question ("laptop
    chargers", answering "Which category are you asking about?") is
    extracted with no idea what it's answering, and the same
    clarification gets asked again no matter what the user replies with.

    `now` defaults to `date.today()` here — the one place in the agent
    layer allowed to call it, since every step downstream (`date_ranges`,
    `intent_extraction`) takes `now` explicitly instead, for testability.
    """
    compiled_graph = build_graph(adapters, category_handlers, settings or Settings())
    final_state = compiled_graph.invoke(
        {
            "raw_question": question,
            "now": now if now is not None else date.today(),
            "history": history or [],
        }
    )
    return AnswerResult(
        text=final_state["answer"],
        metric_series=final_state.get("metric_series", {}),
        comparisons=final_state.get("comparisons", []),
        snapshot=final_state.get("snapshot"),
    )
