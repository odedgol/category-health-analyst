import pytest
from langchain_openai import ChatOpenAI

from category_health.models import (
    ModelProvider,
    build_agent_model,
    load_model_settings,
    local_server_error,
)


def test_openai_settings_keep_backward_compatible_model_variable() -> None:
    settings = load_model_settings(
        environment={
            "OPENAI_API_KEY": "secret",
            "CATEGORY_HEALTH_MODEL": "openai:gpt-test",
        }
    )

    assert settings.provider is ModelProvider.OPENAI
    assert settings.model == "gpt-test"
    assert settings.display_name == "openai:gpt-test"
    assert build_agent_model(settings) == "openai:gpt-test"


def test_unconfigured_settings_are_local_first() -> None:
    settings = load_model_settings(environment={})

    assert settings.provider is ModelProvider.MLX
    assert settings.model == "mlx-community/Qwen3-8B-4bit"


def test_mlx_settings_build_openai_compatible_client_without_openai_key() -> None:
    settings = load_model_settings(
        provider="mlx",
        environment={
            "CATEGORY_HEALTH_MLX_MODEL": "mlx-community/local-test",
            "CATEGORY_HEALTH_MLX_BASE_URL": "http://127.0.0.1:9999/v1/",
        },
    )

    model = build_agent_model(settings)

    assert settings.provider is ModelProvider.MLX
    assert settings.base_url == "http://127.0.0.1:9999/v1"
    assert settings.harness_profile_key == "openai:mlx-community/local-test"
    assert isinstance(model, ChatOpenAI)
    assert str(model.openai_api_base) == "http://127.0.0.1:9999/v1"
    assert model.extra_body == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_openai_requires_key_but_mlx_does_not() -> None:
    openai = load_model_settings(provider="openai", environment={})
    mlx = load_model_settings(provider="mlx", environment={})

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_agent_model(openai)
    assert mlx.configuration_error() is None


def test_openai_rejects_example_placeholder_key() -> None:
    settings = load_model_settings(
        provider="openai", environment={"OPENAI_API_KEY": "your-openai-key"}
    )

    assert "placeholder" in settings.configuration_error()


def test_openai_preflight_never_contacts_a_server() -> None:
    settings = load_model_settings(
        provider="openai", environment={"OPENAI_API_KEY": "secret"}
    )

    assert local_server_error(settings) is None
