"""FACTORY (composition root): the one place concrete adapters get constructed.

`server.py` and, from Sprint 5 onward, `ui/app.py` both call
`build_adapters()` instead of duplicating client/connection setup — every
real DuckDB connection, Chroma client, and provider is constructed exactly
once, here. Nothing outside this module imports `duckdb` or `chromadb`
directly except the adapter modules themselves (`db/`, `rag/`,
`vectorstore.py`).
"""

from dataclasses import dataclass

from category_insights.db.connection import connect
from category_insights.db.repository import DuckDbRepository
from category_insights.rag.notes_store import get_or_create_notes_collection
from category_insights.rag.retriever import ChromaNoteRetriever
from category_insights.settings import Settings
from category_insights.vectorstore import EmbeddingProvider, get_persistent_client


@dataclass(frozen=True)
class AdapterBundle:
    """Every real adapter the MCP server (and, later, the agent) depends on.

    A single bundle rather than separate factory functions so `server.py`
    and `ui/app.py` construct everything in one call and pass the pieces
    they need onward — adding a new adapter later means adding one field
    here, not touching every call site.
    """

    repository: DuckDbRepository
    note_retriever: ChromaNoteRetriever


def build_adapters(settings: Settings) -> AdapterBundle:
    """Construct every adapter from `settings`, ready for real use.

    Not used by tests — test fixtures build fakes or temp-backed adapters
    directly (see `tests/conftest.py`) so tests never depend on this
    function's real DuckDB/Chroma wiring.
    """
    connection = connect(settings.category_insights_db_path)
    repository = DuckDbRepository(connection)

    embedding_function = EmbeddingProvider(settings).get()
    chroma_client = get_persistent_client(settings.category_insights_chroma_dir)
    notes_collection = get_or_create_notes_collection(chroma_client, embedding_function)
    note_retriever = ChromaNoteRetriever(
        notes_collection, min_similarity=settings.category_insights_note_min_similarity
    )

    return AdapterBundle(repository=repository, note_retriever=note_retriever)
