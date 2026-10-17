from pathlib import Path

import pytest

from treesleuth.surnames import (
    SurnameMappingValidationError,
    display_surname,
    load_surname_mappings,
    save_surname_mappings,
)


def test_surname_mappings_persist_by_research_root(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    app_data_root = tmp_path / ".cache"

    mappings = save_surname_mappings(
        first_root,
        {" Edmonds ": "Edmunds"},
        app_data_root,
    )

    assert mappings == {"edmonds": "Edmunds"}
    assert load_surname_mappings(first_root, app_data_root) == mappings
    assert load_surname_mappings(second_root, app_data_root) == {}
    assert display_surname("EDMONDS", mappings) == "Edmunds"
    assert (app_data_root / "surnames").is_dir()
    assert not (first_root / "surname-mappings.json").exists()


def test_surname_mappings_reject_empty_or_conflicting_values(tmp_path: Path) -> None:
    root = tmp_path / "research"
    root.mkdir()

    with pytest.raises(SurnameMappingValidationError, match="must not be empty"):
        save_surname_mappings(root, {"Edmonds": " "}, tmp_path / ".cache")

    with pytest.raises(SurnameMappingValidationError, match="Conflicting"):
        save_surname_mappings(
            root,
            {"Edmonds": "Edmunds", "EDMONDS": "Other"},
            tmp_path / ".cache",
        )
