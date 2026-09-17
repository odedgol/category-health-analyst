"""Conversation history and one audit trace per user turn."""

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import ToolMessage

from category_health.audit import AuditSink, AuditTrail


def _latest_analysis_output(messages: list[object]) -> dict[str, Any] | None:
    """Return the latest structured analysis tool result from model messages."""

    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("status") in {"ok", "partial", "no_data"}
            and "values" in payload
            and "comparisons" in payload
        ):
            return payload
    return None


class AnalysisSession:
    """One local conversation. History advances only after a successful invocation."""

    def __init__(
        self,
        agent,
        audit_sink: AuditSink,
        timezone: str = "Asia/Jerusalem",
        today: date | None = None,
        session_id: str | None = None,
        trace_name: str = "category-health-agent-request",
        trace_tags: tuple[str, ...] = ("category-health", "agent"),
    ) -> None:
        self.agent = agent
        self.audit_sink = audit_sink
        self.timezone = ZoneInfo(timezone)
        self.messages = []
        self.last_trace_id = None
        self.last_analysis_output: dict[str, Any] | None = None
        self.today = today
        self.session_id = session_id
        self.trace_name = trace_name
        self.trace_tags = trace_tags

    def ask(self, question: str):
        if not question.strip():
            raise ValueError("Please enter a question.")
        self.last_analysis_output = None
        audit = AuditTrail(
            self.audit_sink,
            trace_name=self.trace_name,
            session_id=self.session_id,
            tags=self.trace_tags,
        )
        self.last_trace_id = audit.trace_id
        today = (self.today or datetime.now(self.timezone).date()).isoformat()
        with audit.as_current():
            with audit.step(
                "user_request",
                input_summary={"question_length": len(question), "today": today},
                input_object={"question": question, "today": today},
            ) as request_step:
                callbacks = getattr(self.audit_sink, "langchain_callbacks", lambda: [])()
                invocation_config = {"recursion_limit": 20}
                if callbacks:
                    invocation_config["callbacks"] = callbacks
                result = self.agent.invoke(
                    {
                        "messages": [
                            *self.messages,
                            {"role": "user", "content": f"Today is {today}.\n{question}"},
                        ]
                    },
                    config=invocation_config,
                )
                with audit.step("model_messages") as step:
                    step.set_output_object(result["messages"])
                with audit.step("final_answer") as step:
                    step.set_output_object(result["messages"][-1].content)
                answer_content = result["messages"][-1].content
                request_step.set_output(
                    {
                        "status": "ok",
                        "answer_length": len(str(answer_content)),
                    }
                )
                request_step.set_output_object(
                    {"status": "ok", "answer": answer_content}
                )
                self.messages = result["messages"]
                self.last_analysis_output = _latest_analysis_output(self.messages)
                return result["messages"][-1]
