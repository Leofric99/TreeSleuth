import json
from pathlib import Path

from treesleuth.analysis import AuditResponse, BiographyResponse
from treesleuth.results import save_analysis_results


def test_saves_biography_conflicts_and_source_provenance(tmp_path: Path) -> None:
    biography = BiographyResponse(
        biography="Ada Lovelace was born in London.",
        claims=[
            {
                "claim": "Ada was born in London.",
                "source_ids": ["gedcom:tree#@I1@:birth", "record-1"],
                "inferred": False,
            }
        ],
    )
    conflicts = AuditResponse(
        findings=[
            {
                "outcome": "conflict",
                "person_id": "tree#@I1@",
                "source_document_id": "record-1",
                "source_claim": "Record says 1860.",
                "baseline_source_id": "gedcom:tree#@I1@:death",
                "baseline_claim": "Died in 1852.",
                "explanation": "Source date is after recorded death.",
                "confidence": 0.9,
            }
        ]
    )

    app_data_root = tmp_path / ".cache"
    saved = save_analysis_results(
        tmp_path,
        "tree#@I1@",
        "Ada Lovelace",
        biography,
        conflicts,
        app_data_root=app_data_root,
    )

    assert saved.biography_path.is_file()
    assert "Ada Lovelace" in saved.biography_path.read_text(encoding="utf-8")
    assert saved.biography_path.is_relative_to(app_data_root)
    assert not (tmp_path / "output").exists()
    conflict_data = json.loads(saved.conflicts_path.read_text(encoding="utf-8"))
    assert conflict_data["findings"][0]["source_document_id"] == "record-1"
    assert conflict_data["findings"][0]["baseline_source_id"] == "gedcom:tree#@I1@:death"
    analysis_data = json.loads(saved.analysis_path.read_text(encoding="utf-8"))
    assert analysis_data["biography"]["claims"][0]["source_ids"] == [
        "gedcom:tree#@I1@:birth",
        "record-1",
    ]


def test_same_display_name_for_different_people_has_distinct_outputs(tmp_path: Path) -> None:
    biography = BiographyResponse(
        biography="A documented life.",
        claims=[{"claim": "A documented fact.", "source_ids": ["doc"], "inferred": False}],
    )
    conflicts = AuditResponse(findings=[])

    app_data_root = tmp_path / ".cache"
    first = save_analysis_results(
        tmp_path, "tree#@I1@", "Alex Smith", biography, conflicts, app_data_root=app_data_root
    )
    second = save_analysis_results(
        tmp_path, "tree#@I2@", "Alex Smith", biography, conflicts, app_data_root=app_data_root
    )

    assert first.biography_path != second.biography_path
    assert first.biography_path.exists()
    assert second.biography_path.exists()


def test_output_filename_cannot_escape_application_data_root(tmp_path: Path) -> None:
    biography = BiographyResponse(
        biography="A documented life.",
        claims=[{"claim": "A documented fact.", "source_ids": ["doc"], "inferred": False}],
    )
    conflicts = AuditResponse(findings=[])

    app_data_root = tmp_path / ".cache"
    saved = save_analysis_results(
        tmp_path,
        "../outside/name",
        "../../outside",
        biography,
        conflicts,
        app_data_root=app_data_root,
    )

    assert saved.biography_path.is_relative_to(app_data_root.resolve())
    assert saved.conflicts_path.is_relative_to(app_data_root.resolve())


def test_results_use_only_application_cache_when_it_is_inside_selected_root(tmp_path: Path) -> None:
    biography = BiographyResponse(
        biography="A documented life.",
        claims=[{"claim": "A documented fact.", "source_ids": ["doc"], "inferred": False}],
    )
    conflicts = AuditResponse(findings=[])
    app_data_root = tmp_path / ".cache"

    saved = save_analysis_results(
        tmp_path,
        "tree#@I1@",
        "Ada Lovelace",
        biography,
        conflicts,
        app_data_root=app_data_root,
    )

    assert saved.biography_path.is_relative_to(app_data_root.resolve())
    assert not (tmp_path / "output").exists()
