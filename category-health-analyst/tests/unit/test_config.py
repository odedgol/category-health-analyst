import os

from category_health.config import load_local_environment


def test_loads_only_explicit_env_without_overriding_shell_values(
    tmp_path, monkeypatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    environment_file = project / ".env"
    environment_file.write_text(
        "FROM_PARENT=loaded\nPRESERVED=from-file\n", encoding="utf-8"
    )
    monkeypatch.setenv("PRESERVED", "from-shell")
    monkeypatch.delenv("FROM_PARENT", raising=False)

    loaded = load_local_environment(environment_file)

    assert loaded == environment_file
    assert os.environ["FROM_PARENT"] == "loaded"
    assert os.environ["PRESERVED"] == "from-shell"


def test_does_not_search_parent_directories(tmp_path, monkeypatch) -> None:
    project = tmp_path / "workspace" / "project"
    project.mkdir(parents=True)
    (tmp_path / "workspace" / ".env").write_text(
        "PARENT_ONLY=must-not-load\n", encoding="utf-8"
    )
    monkeypatch.delenv("PARENT_ONLY", raising=False)

    loaded = load_local_environment(project / ".env")

    assert loaded is None
    assert "PARENT_ONLY" not in os.environ
