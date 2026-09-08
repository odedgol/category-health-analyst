"""Loads the curated analyst-notes corpus from `fixtures/category_notes.yaml`.

Kept separate from `mock_data.py` (which generates the numeric metric
snapshots) because these two are deliberately different tracks: this
module feeds the RAG index, `mock_data.py` feeds the DuckDB warehouse —
mirroring the production split between structured tool-calling and
retrieval that the rest of the codebase preserves.
"""

from pathlib import Path

import yaml

from category_insights.domain.models import Note

DEFAULT_NOTES_PATH = Path("fixtures/category_notes.yaml")


def load_notes(notes_path: Path = DEFAULT_NOTES_PATH) -> list[Note]:
    """Load and validate every note in the corpus."""
    raw = yaml.safe_load(notes_path.read_text())
    return [Note.model_validate(entry) for entry in raw["notes"]]
