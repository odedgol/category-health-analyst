"""Local environment loading shared by the UI and command-line entry points."""

from pathlib import Path

from dotenv import load_dotenv


def load_local_environment(environment_file: Path) -> Path | None:
    """Load one explicit project-local ``.env`` without searching parent folders."""

    path = environment_file.resolve()
    if not path.is_file():
        return None
    load_dotenv(path, override=False)
    return path
