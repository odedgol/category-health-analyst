"""Builds the `category_notes` Chroma collection from the curated notes corpus.

Ingestion only — querying it lives in `retriever.py`. Kept as a separate
function/module from retrieval so the "build the index" and "search the
index" concerns can be tested and reasoned about independently, and so
`scripts/seed_notes_index.py` can rebuild the index without importing
anything retrieval-related.
"""

import re

import chromadb
from chromadb.api.types import EmbeddingFunction

from category_insights.domain.models import Note

COLLECTION_NAME = "category_notes"
_MAX_CHUNK_CHARS = 400

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def chunk_note_body(body: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    """Split a note's body into chunks at sentence boundaries, up to `max_chars` each.

    The corpus is curated to be short and realistic (1-3 sentences per
    note), so most notes produce exactly one chunk — this only matters
    for the rare note that runs long.
    """
    body = body.strip()
    if len(body) <= max_chars:
        return [body]

    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_BOUNDARY.split(body):
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def get_or_create_notes_collection(
    client: chromadb.ClientAPI, embedding_function: EmbeddingFunction
) -> chromadb.Collection:
    """Return the `category_notes` collection, creating it (cosine space) if absent."""
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )


def build_notes_index(collection: chromadb.Collection, notes: list[Note]) -> None:
    """(Re)populate `collection` from `notes`. Assumes an empty or freshly reset collection."""
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str | int]] = []

    for note in notes:
        for chunk_index, chunk_body in enumerate(chunk_note_body(note.body)):
            ids.append(f"{note.category_id}-{note.date.isoformat()}-{chunk_index}")
            documents.append(chunk_body)
            metadatas.append({"category_id": note.category_id, "date": note.date.isoformat()})

    if ids:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
