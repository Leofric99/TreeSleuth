from pathlib import Path

import pytest

from treesleuth.paths import PathValidationError, ensure_within_root, validate_research_root


def test_validate_research_root_resolves_directory(tmp_path: Path) -> None:
    assert validate_research_root(tmp_path) == tmp_path.resolve()


def test_validate_research_root_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(PathValidationError, match="does not exist"):
        validate_research_root(tmp_path / "missing")


def test_validate_research_root_rejects_regular_file(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("research", encoding="utf-8")

    with pytest.raises(PathValidationError, match="not a directory"):
        validate_research_root(source)


def test_validate_research_root_rejects_unreadable_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("treesleuth.paths.os.access", lambda *_args: False)

    with pytest.raises(PathValidationError, match="not readable"):
        validate_research_root(tmp_path)


def test_ensure_within_root_rejects_outside_path(tmp_path: Path) -> None:
    root = tmp_path / "research"
    root.mkdir()
    outside = tmp_path / "outside.txt"

    with pytest.raises(PathValidationError, match="outside"):
        ensure_within_root(root, outside)


def test_ensure_within_root_allows_descendant(tmp_path: Path) -> None:
    root = tmp_path / "research"
    root.mkdir()
    output = root / "output"

    assert ensure_within_root(root, output) == output.resolve()
