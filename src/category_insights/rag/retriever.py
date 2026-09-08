"""`NoteRetriever` implementation backed by the `category_notes` Chroma collection.

Always filters by `category_id` as a metadata `where` clause — applied by
Chroma as part of the query itself, before ranking — so a note about a
different category can never leak into an answer no matter how similar
its wording. Chunks below `min_similarity` are dropped rather than
returned as a low-confidence guess: an empty list is the honest answer
when nothing relevant was found.
"""

from datetime import date

import chromadb

from category_insights.domain.models import NoteChunk


class ChromaNoteRetriever:
    """Adapter implementing `domain.ports.NoteRetriever` against a Chroma collection."""

    def __init__(self, collection: chromadb.Collection, min_similarity: float) -> None:
        self._collection = collection
        self._min_similarity = min_similarity

    def retrieve_category_notes(
        self, category_id: int, query: str, top_k: int = 3
    ) -> list[NoteChunk]:
        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"category_id": category_id},
        )

        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        chunks: list[NoteChunk] = []
        for chunk_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            # Cosine space (configured when the collection is created): distance = 1 - similarity.
            score = 1.0 - distance
            if score < self._min_similarity:
                continue
            chunks.append(
                NoteChunk(
                    category_id=int(metadata["category_id"]),
                    date=date.fromisoformat(str(metadata["date"])),
                    body=document,
                    score=score,
                    chunk_id=chunk_id,
                )
            )

        chunks.sort(key=lambda chunk: chunk.score, reverse=True)
        return chunks
