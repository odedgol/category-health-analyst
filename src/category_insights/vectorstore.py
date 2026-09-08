"""Shared Chroma client + embedding-function provider.

Both `rag/notes_store.py` (grounding "why" answers) and
`agent/category_resolution.py` (resolving loose category mentions) need a
Chroma-backed vector collection, but per the spec they must never share
one collection. This module exists only to avoid duplicating client and
embedding-function setup between them — it is infrastructure, not a port,
and the two collections built on top of it stay semantically and
physically separate (different collection names, different purposes).
"""

from pathlib import Path

import chromadb
from chromadb.api.types import EmbeddingFunction
from chromadb.utils import embedding_functions

from category_insights.settings import Settings


class EmbeddingProvider:
    """PROVIDER: supplies a configured Chroma embedding function.

    The one place `OPENAI_API_KEY`/`OPENAI_EMBEDDING_MODEL` are read to
    build an embedding function — everything downstream (both vector
    collections) depends on the callable this returns, never on this
    class or on OpenAI directly. Swapping embedding providers is a
    one-file change.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def get(self) -> EmbeddingFunction:
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=self._settings.openai_api_key,
            model_name=self._settings.openai_embedding_model,
        )


def get_persistent_client(persist_directory: Path) -> chromadb.ClientAPI:
    """Open (creating if absent) a Chroma client persisted at `persist_directory`."""
    persist_directory.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_directory))
