from pathlib import Path

import pytest

from treesleuth.discovery import scan_directory


def test_scan_directory_discovers_nested_mixed_files_case_insensitively(tmp_path: Path) -> None:
    (tmp_path / "tree").mkdir()
    (tmp_path / "papers" / "archive").mkdir(parents=True)
    (tmp_path / "tree" / "Family.GED").write_text("0 HEAD", encoding="utf-8")
    (tmp_path / "papers" / "archive" / "Record.PDF").write_bytes(b"pdf")
    (tmp_path / "papers" / "photo.TIFF").write_bytes(b"image")
    (tmp_path / "papers" / "notes.Md").write_text("notes", encoding="utf-8")
    (tmp_path / "papers" / "readme.txt").write_text("notes", encoding="utf-8")
    (tmp_path / "papers" / "unknown.doc").write_text("ignored", encoding="utf-8")

    result = scan_directory(tmp_path)

    assert [item.kind for item in result.gedcom_files] == ["gedcom"]
    assert len(result.document_files) == 4
    assert result.files_by_type == {"gedcom": 1, "pdf": 1, "image": 1, "text": 2}


def test_scan_directory_excludes_cache_and_output_trees(tmp_path: Path) -> None:
    (tmp_path / ".tree_cache").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "records").mkdir()
    (tmp_path / ".tree_cache" / "cached.txt").write_text("cached", encoding="utf-8")
    (tmp_path / "output" / "story.txt").write_text("generated", encoding="utf-8")
    (tmp_path / "records" / "source.txt").write_text("source", encoding="utf-8")

    result = scan_directory(tmp_path)

    assert [item.relative_path for item in result.document_files] == [Path("records") / "source.txt"]


def test_scan_directory_does_not_follow_directory_symlink_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "research"
    outside = tmp_path / "external"
    root.mkdir()
    outside.mkdir()
    (outside / "private.txt").write_text("external", encoding="utf-8")
    link = root / "external-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable on this host")

    result = scan_directory(root)

    assert not result.document_files
