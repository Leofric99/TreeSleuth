from pathlib import Path
from types import SimpleNamespace

import pytest

from treesleuth.extraction import DoclingExtractor, DocumentExtractionError


class FakeConverter:
    def __init__(self, text: str = "recognized record", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.sources: list[Path] = []

    def convert(self, source: Path) -> SimpleNamespace:
        self.sources.append(source)
        if self.error:
            raise self.error
        return SimpleNamespace(document=SimpleNamespace(export_to_markdown=lambda: self.text))


@pytest.mark.parametrize("suffix", [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"])
def test_docling_formats_use_cpu_when_acceleration_is_disabled(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"record{suffix}"
    source.write_bytes(b"fixture")
    used_devices: list[str] = []
    converter = FakeConverter()

    def factory(device: str) -> FakeConverter:
        used_devices.append(device)
        return converter

    extractor = DoclingExtractor(use_acceleration=False, converter_factory=factory)

    assert extractor.extract_text(source) == "recognized record"
    assert used_devices == ["cpu"]
    assert converter.sources == [source]


@pytest.mark.parametrize("suffix", [".txt", ".md", ".markdown"])
def test_text_notes_are_read_directly(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"notes{suffix}"
    source.write_text("Research note", encoding="utf-8")
    extractor = DoclingExtractor(converter_factory=lambda _device: pytest.fail("OCR must not run for text"))

    assert extractor.extract_text(source) == "Research note"


def test_accelerated_failure_retries_on_cpu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "record.pdf"
    source.write_bytes(b"fixture")
    attempts: list[str] = []
    converters = {
        "cuda": FakeConverter(error=RuntimeError("GPU unavailable")),
        "cpu": FakeConverter("CPU result"),
    }

    def factory(device: str) -> FakeConverter:
        attempts.append(device)
        return converters[device]

    monkeypatch.setattr("treesleuth.extraction._detect_accelerator", lambda: "cuda")
    extractor = DoclingExtractor(use_acceleration=True, converter_factory=factory)

    assert extractor.extract_text(source) == "CPU result"
    assert attempts == ["cuda", "cpu"]


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_docling_output_is_an_error(tmp_path: Path, text: str) -> None:
    source = tmp_path / "record.pdf"
    source.write_bytes(b"fixture")
    extractor = DoclingExtractor(
        use_acceleration=False,
        converter_factory=lambda _device: FakeConverter(text),
    )

    with pytest.raises(DocumentExtractionError, match="No readable text"):
        extractor.extract_text(source)


def test_text_read_failure_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("content", encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("denied")))
    extractor = DoclingExtractor(use_acceleration=False)

    with pytest.raises(DocumentExtractionError, match="Unable to read"):
        extractor.extract_text(source)


def test_docling_failure_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "record.pdf"
    source.write_bytes(b"fixture")
    extractor = DoclingExtractor(
        use_acceleration=False,
        converter_factory=lambda _device: FakeConverter(error=RuntimeError("OCR failed")),
    )

    with pytest.raises(DocumentExtractionError, match="Docling failed"):
        extractor.extract_text(source)


def test_acceleration_is_selected_by_default_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "record.pdf"
    source.write_bytes(b"fixture")
    used_devices: list[str] = []

    def factory(device: str) -> FakeConverter:
        used_devices.append(device)
        return FakeConverter()

    monkeypatch.setattr("treesleuth.extraction._detect_accelerator", lambda: "cuda")
    extractor = DoclingExtractor(converter_factory=factory)

    assert extractor.extract_text(source) == "recognized record"
    assert used_devices == ["cuda"]
