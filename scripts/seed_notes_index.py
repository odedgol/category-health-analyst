"""CLI: (re)build the category-notes vector index, independent of the metrics DB seed.

Usage:
    uv run python -m scripts.seed_notes_index --reset
"""

import argparse
import contextlib
from pathlib import Path

import chromadb.errors

from category_insights.mock_notes import DEFAULT_NOTES_PATH, load_notes
from category_insights.rag.notes_store import build_notes_index, get_or_create_notes_collection
from category_insights.settings import Settings
from category_insights.vectorstore import EmbeddingProvider, get_persistent_client


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the category-notes vector index.")
    parser.add_argument("--reset", action="store_true", help="Delete and rebuild the collection.")
    parser.add_argument(
        "--notes", type=Path, default=DEFAULT_NOTES_PATH, help="Path to the notes corpus YAML."
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    settings = Settings()

    client = get_persistent_client(settings.category_insights_chroma_dir)
    if args.reset:
        with contextlib.suppress(chromadb.errors.NotFoundError):
            client.delete_collection(name="category_notes")  # nothing to reset on a first run

    embedding_function = EmbeddingProvider(settings).get()
    collection = get_or_create_notes_collection(client, embedding_function)

    notes = load_notes(args.notes)
    build_notes_index(collection, notes)
    print(f"Indexed {len(notes)} notes into the '{collection.name}' collection.")  # noqa: T201


if __name__ == "__main__":
    main()
