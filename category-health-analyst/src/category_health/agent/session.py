"""Conversation history and one audit trace per user turn."""

import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import ToolMessage

from category_health.audit import AuditSink, AuditTrail, StepAuditContext


def find_latest_analysis_result(messages: list[object]) -> dict[str, Any] | None:
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
        """Run one audited conversation turn and commit successful history."""

        question = self._validate_question(question)
        self.last_analysis_output = None
        audit = self._start_turn_audit()
        today = self._today()

        with audit.as_current():
            with audit.step(
                "user_request",
                input_summary={"question_length": len(question), "today": today},
                input_object={"question": question, "today": today},
            ) as request_step:
                messages = self._invoke_agent(question, today)
                return self._complete_turn(messages, audit, request_step)

    @staticmethod
    def _validate_question(question: str) -> str:
        question = question.strip()
        if not question:
            raise ValueError("Please enter a question.")
        return question

    def _invoke_agent(self, question: str, today: str) -> list[object]:
        result = self.agent.invoke(
            {"messages": self._messages_for_turn(question, today)},
            config=self._invocation_config(),
        )
        return result["messages"]

    def _complete_turn(
        self,
        messages: list[object],
        audit: AuditTrail,
        request_step: StepAuditContext,
    ):
        answer = messages[-1]
        self._audit_model_result(audit, messages, answer.content)
        request_step.set_output(
            {"status": "ok", "answer_length": len(str(answer.content))}
        )
        request_step.set_output_object({"status": "ok", "answer": answer.content})
        self.messages = messages
        self.last_analysis_output = find_latest_analysis_result(messages)
        return answer

    def _start_turn_audit(self) -> AuditTrail:
        audit = AuditTrail(
            self.audit_sink,
            trace_name=self.trace_name,
            session_id=self.session_id,
            tags=self.trace_tags,
        )
        self.last_trace_id = audit.trace_id
        return audit

    def _today(self) -> str:
        return (self.today or datetime.now(self.timezone).date()).isoformat()

    def _messages_for_turn(self, question: str, today: str) -> list[object]:
        return [
            *self.messages,
            {"role": "user", "content": f"Today is {today}.\n{question}"},
        ]

    def _invocation_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {"recursion_limit": 20}
        callbacks = getattr(self.audit_sink, "langchain_callbacks", lambda: [])()
        if callbacks:
            config["callbacks"] = callbacks
        return config

    @staticmethod
    def _audit_model_result(
        audit: AuditTrail,
        messages: list[object],
        answer: object,
    ) -> None:
        with audit.step("model_messages") as step:
            step.set_output_object(messages)
        with audit.step("final_answer") as step:
            step.set_output_object(answer)
