"""Conversation history and one audit trace per user turn."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from category_health.audit import AuditSink, AuditTrail, current_audit


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
        self.today = today
        self.session_id = session_id
        self.trace_name = trace_name
        self.trace_tags = trace_tags

    def ask(self, question: str):
        if not question.strip():
            raise ValueError("Please enter a question.")
        audit = AuditTrail(
            self.audit_sink,
            trace_name=self.trace_name,
            session_id=self.session_id,
            tags=self.trace_tags,
        )
        self.last_trace_id = audit.trace_id
        token = current_audit.set(audit)
        today = (self.today or datetime.now(self.timezone).date()).isoformat()
        try:
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
                return result["messages"][-1]
        finally:
            current_audit.reset(token)
