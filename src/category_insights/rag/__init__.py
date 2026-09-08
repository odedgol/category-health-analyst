"""RAG layer: the adapter implementing `NoteRetriever` against a Chroma collection.

`notes_store.py` builds the `category_notes` collection from the curated
corpus (`mock_notes.py`); `retriever.py` queries it, always filtering by
`category_id` before ranking by similarity. This is the retrieval track
that grounds "why did X change" answers — kept deliberately separate from
`agent/category_resolution.py`'s vector index, which resolves category
mentions and is a different job with a different collection.
"""
