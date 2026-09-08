"""Application configuration, read from the environment exactly once.

This is the only module in the codebase that reads `os.environ` (via
`pydantic-settings`). Every other module receives configuration through a
`Settings` instance passed in explicitly, so nothing else needs to know
where a value came from or be monkeypatched to change it in tests.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the agent, the MCP server, and the UI.

    Field names match the `.env.example` keys (case-insensitive). Only the
    OpenAI-compatible LLM fields are required for a real run; everything
    else has a workable default so `Settings()` succeeds in tests without
    an `.env` file.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = Field(default="", description="API key for the chat + embedding models.")
    openai_model: str = Field(default="gpt-4o-mini", description="Chat model name.")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", description="Embedding model name."
    )

    category_insights_db_path: Path = Field(default=Path("data/warehouse.duckdb"))
    category_insights_chroma_dir: Path = Field(default=Path("data/chroma"))

    category_insights_resolution_high_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    category_insights_resolution_medium_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    category_insights_note_min_similarity: float = Field(default=0.3, ge=0.0, le=1.0)
    category_insights_unexpected_delta_threshold: float = Field(default=10.0, ge=0.0)
    category_insights_mock_data_seed: int = Field(default=42)
