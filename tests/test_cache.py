import json
from pathlib import Path

from treesleuth.cache import ExtractionCache


def test_cache_reuses_unchanged_document(tmp_path: Path) -> None:
    source = tmp_path / "record.txt"
    source.write_text("source text", encoding="utf-8")
    cache = ExtractionCache(tmp_path, "plain-text-v1")
    calls: list[Path] = []

    def extract(path: Path) -> str:
        calls.append(path)
        return "extracted text"

    first = cache.get_or_extract(source, extract)
    second = cache.get_or_extract(source, extract)

    assert first.text == "extracted text"
    assert not first.cache_hit
    assert second.cache_hit
    assert second.text == first.text
    assert calls == [source]


def test_cache_reextracts_and_replaces_changed_source(tmp_path: Path) -> None:
    source = tmp_path / "record.txt"
    source.write_text("first version", encoding="utf-8")
    cache = ExtractionCache(tmp_path, "docling-v1")
    results = iter(["first extraction", "updated extraction"])

    first = cache.get_or_extract(source, lambda _path: next(results))
    source.write_text("second version", encoding="utf-8")
    second = cache.get_or_extract(source, lambda _path: next(results))
    third = cache.get_or_extract(source, lambda _path: "should not be used")

    assert first.text == "first extraction"
    assert second.text == "updated extraction"
    assert any("stale" in item for item in second.warnings)
    assert third.cache_hit
    cache_files = list((tmp_path / ".tree_cache").glob("*.json"))
    assert len(cache_files) == 1


def test_cache_invalidates_when_extractor_identity_changes(tmp_path: Path) -> None:
    source = tmp_path / "record.txt"
    source.write_text("source text", encoding="utf-8")
    old_cache = ExtractionCache(tmp_path, "docling-v1")
    new_cache = ExtractionCache(tmp_path, "docling-v2")
    old_cache.get_or_extract(source, lambda _path: "old extraction")

    result = new_cache.get_or_extract(source, lambda _path: "new extraction")

    assert result.text == "new extraction"
    assert not result.cache_hit


def test_cache_read_failure_falls_back_to_extraction(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "record.txt"
    source.write_text("source text", encoding="utf-8")
    cache = ExtractionCache(tmp_path, "plain-v1")
    cache_path = cache._cache_path(source)
    cache_path.parent.mkdir()
    cache_path.write_text("not json", encoding="utf-8")

    result = cache.get_or_extract(source, lambda _path: "fresh text")

    assert result.text == "fresh text"
    assert not result.cache_hit
    assert result.warnings
    assert json.loads(cache_path.read_text(encoding="utf-8"))["text"] == "fresh text"


def test_cache_write_failure_returns_extraction_with_warning(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "record.txt"
    source.write_text("source text", encoding="utf-8")
    cache = ExtractionCache(tmp_path, "plain-v1")
    original_mkdir = Path.mkdir

    def fail_cache_directory(path: Path, *args, **kwargs) -> None:
        if path == cache.cache_directory:
            raise OSError("read-only cache")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_cache_directory)

    result = cache.get_or_extract(source, lambda _path: "fresh text")

    assert result.text == "fresh text"
    assert not result.cache_hit
    assert any("Could not write cache" in warning for warning in result.warnings)
