"""Configure the hosted OpenAI or local MLX language-model provider."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.error import URLError
from urllib.request import Request, urlopen

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI


class ModelProvider(StrEnum):
    """The two inference backends supported by this project."""

    OPENAI = "openai"
    MLX = "mlx"


@dataclass(frozen=True)
class ModelSettings:
    """Non-secret model identity plus the credential used to create its client."""

    provider: ModelProvider
    model: str
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None

    @property
    def display_name(self) -> str:
        return f"{self.provider.value}:{self.model}"

    @property
    def harness_profile_key(self) -> str:
        # MLX exposes an OpenAI-compatible endpoint and is represented by ChatOpenAI.
        provider = "openai" if self.provider is ModelProvider.MLX else self.provider.value
        return f"{provider}:{self.model}"

    def configuration_error(self) -> str | None:
        if self.provider is ModelProvider.OPENAI:
            if not self.api_key:
                return "OPENAI_API_KEY is not configured in the project environment."
            if self.api_key.lower().startswith(("your-", "replace-", "example-")):
                return "OPENAI_API_KEY still contains an example placeholder."
        if self.provider is ModelProvider.MLX and not self.base_url:
            return "CATEGORY_HEALTH_MLX_BASE_URL is not configured."
        return None


def _strip_openai_prefix(model: str) -> str:
    return model.removeprefix("openai:")


def load_model_settings(
    *,
    provider: str | ModelProvider | None = None,
    model: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> ModelSettings:
    """Resolve one provider without reading or searching for environment files."""

    values = environment if environment is not None else os.environ
    selected_provider = provider or values.get("CATEGORY_HEALTH_PROVIDER")
    if selected_provider is None:
        # Preserve the original one-variable OpenAI configuration while making a
        # completely unconfigured installation local-first.
        selected_provider = (
            "openai"
            if "CATEGORY_HEALTH_MODEL" in values
            or "CATEGORY_HEALTH_OPENAI_MODEL" in values
            else "mlx"
        )
    selected = ModelProvider(selected_provider)
    if selected is ModelProvider.OPENAI:
        selected_model = model or values.get(
            "CATEGORY_HEALTH_OPENAI_MODEL",
            values.get("CATEGORY_HEALTH_MODEL", "openai:gpt-5.4-mini"),
        )
        return ModelSettings(
            provider=selected,
            model=_strip_openai_prefix(selected_model),
            api_key=values.get("OPENAI_API_KEY"),
        )

    return ModelSettings(
        provider=selected,
        model=model
        or values.get(
            "CATEGORY_HEALTH_MLX_MODEL",
            "mlx-community/Qwen3-8B-4bit",
        ),
        api_key=values.get("CATEGORY_HEALTH_MLX_API_KEY", "not-needed"),
        base_url=values.get(
            "CATEGORY_HEALTH_MLX_BASE_URL", "http://127.0.0.1:8080/v1"
        ).rstrip("/"),
    )


def build_agent_model(settings: ModelSettings) -> str | BaseChatModel:
    """Build the value Deep Agents consumes for the selected provider."""

    error = settings.configuration_error()
    if error:
        raise ValueError(error)
    if settings.provider is ModelProvider.OPENAI:
        # Keep Deep Agents' native OpenAI initialization and Responses API behavior.
        return f"openai:{settings.model}"
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=0,
        max_retries=0,
        use_responses_api=False,
        tiktoken_model_name="gpt-4o",
        # Qwen3 reasoning variants can spend the server's entire default output
        # budget on hidden thinking before producing a tool call. Routing is a
        # narrow task, so disable thinking for every MLX request.
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )


def local_server_error(settings: ModelSettings, *, timeout: float = 2) -> str | None:
    """Return a readable MLX preflight error without contacting hosted providers."""

    if settings.provider is not ModelProvider.MLX:
        return None
    request = Request(
        f"{settings.base_url}/models",
        headers={"Authorization": f"Bearer {settings.api_key}"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - localhost by config
            if response.status == 200:
                return None
            return f"MLX server returned HTTP {response.status}."
    except (OSError, URLError) as error:
        return (
            f"MLX server is not reachable at {settings.base_url}. "
            "Start mlx_lm.server before running a live MLX evaluation "
            f"({type(error).__name__})."
        )
