"""PROVIDER: `ChatModelProvider` — the one place the chat model provider/model is chosen.

Every other module depends on `domain.ports.ChatModel`, never on
`langchain_openai` or any provider-specific type — swapping providers
means changing this file only.
"""

from langchain_openai import ChatOpenAI

from category_insights.domain.ports import ChatModel
from category_insights.settings import Settings


class ChatModelProvider:
    """Supplies a configured chat model, built from `Settings`."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get(self) -> ChatModel:
        return ChatOpenAI(
            api_key=self._settings.openai_api_key,
            model=self._settings.openai_model,
            temperature=0,
        )
