import io
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from treesleuth.config import Settings
from treesleuth.extraction import (
    DocumentExtractionError,
    VlmExtractor,
    render_pages,
    vlm_extraction_identity,
)


class FakeClient:
    def __init__(self, replies: list[str] | None = None, error: Exception | None = None) -> None:
        self.replies = list(replies or ["transcribed record"])
        self.error = error
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return {"message": {"content": reply}}


def renderer(pages: int):
    return lambda _source: iter([b"png"] * pages)


@pytest.mark.parametrize("suffix", [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"])
def test_scanned_formats_are_sent_to_the_selected_model(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"record{suffix}"
    source.write_bytes(b"fixture")
    client = FakeClient()
    extractor = VlmExtractor(Settings(), "vision-model", client=client, renderer=renderer(1))

    assert extractor.extract_text(source) == "transcribed record"
    assert client.calls[0]["model"] == "vision-model"
    # Each rendered page is checked; if < 1920px stays as-is, otherwise chunked
    assert client.calls[0]["messages"][0]["images"] == [b"png"]


def test_multiple_pages_are_combined_in_order(tmp_path: Path) -> None:
    source = tmp_path / "book.pdf"
    source.write_bytes(b"fixture")
    pages: list[tuple[Path, int]] = []
    extractor = VlmExtractor(
        Settings(),
        "vision-model",
        client=FakeClient(["first", "second"]),
        renderer=renderer(2),
        on_page=lambda path, number: pages.append((path, number)),
    )

    assert extractor.extract_text(source) == "--- Page 1 ---\n\nfirst\n\n--- Page 2 ---\n\nsecond"
    assert pages == [(source, 1), (source, 2)]
    # Each small (< 1920) page gets 1 call
    assert len(extractor._client.calls) == 2


@pytest.mark.parametrize("suffix", [".txt", ".md", ".markdown"])
def test_text_notes_are_read_without_a_model(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"notes{suffix}"
    source.write_text("  John lived in Leeds  ", encoding="utf-8")
    client = FakeClient(error=AssertionError("VLM must not run for text"))

    assert VlmExtractor(Settings(), None, client=client).extract_text(source) == "John lived in Leeds"
    assert client.calls == []


def test_empty_transcription_is_an_error(tmp_path: Path) -> None:
    source = tmp_path / "blank.png"
    source.write_bytes(b"fixture")
    extractor = VlmExtractor(Settings(), "vision-model", client=FakeClient(["  "]), renderer=renderer(1))

    with pytest.raises(DocumentExtractionError, match="No readable text"):
        extractor.extract_text(source)


def test_model_failure_names_document_and_page(tmp_path: Path) -> None:
    source = tmp_path / "record.png"
    source.write_bytes(b"fixture")
    extractor = VlmExtractor(
        Settings(),
        "vision-model",
        client=FakeClient(error=TimeoutError("timed out")),
        renderer=renderer(1),
    )

    with pytest.raises(DocumentExtractionError, match="page 1.*tile.*record.png: timed out"):
        extractor.extract_text(source)


def test_scanned_document_requires_a_model(tmp_path: Path) -> None:
    source = tmp_path / "record.png"
    source.write_bytes(b"fixture")

    with pytest.raises(DocumentExtractionError, match="vision model must be selected"):
        VlmExtractor(Settings(), None, client=FakeClient()).extract_text(source)


def test_unsupported_and_corrupt_files_are_explicit(tmp_path: Path) -> None:
    unsupported = tmp_path / "record.docx"
    unsupported.write_bytes(b"fixture")
    corrupt = tmp_path / "record.png"
    corrupt.write_bytes(b"not an image")
    extractor = VlmExtractor(Settings(), "vision-model", client=FakeClient())

    with pytest.raises(DocumentExtractionError, match="Unsupported"):
        extractor.extract_text(unsupported)
    with pytest.raises(DocumentExtractionError, match="Unable to render"):
        extractor.extract_text(corrupt)


def test_identity_changes_with_model_and_settings() -> None:
    base = vlm_extraction_identity(Settings(), "a")

    assert base != vlm_extraction_identity(Settings(), "b")
    assert base != vlm_extraction_identity(Settings(vlm_prompt="other"), "a")
    assert base != vlm_extraction_identity(Settings(vlm_pdf_dpi=300), "a")
    assert base != vlm_extraction_identity(Settings(vlm_max_image_side=1024), "a")


def test_render_pages_handles_pdf_and_multiframe_tiff(tmp_path: Path) -> None:
    pdf = tmp_path / "book.pdf"
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "page one")
    document.new_page().insert_text((72, 72), "page two")
    document.save(pdf)
    document.close()
    tiff = tmp_path / "scan.tiff"
    frames = [Image.new("RGB", (4000, 100), color) for color in ("white", "black")]
    frames[0].save(tiff, save_all=True, append_images=frames[1:])

    pdf_pages = list(render_pages(pdf, dpi=72, max_side=2048))
    tiff_pages = list(render_pages(tiff, dpi=72, max_side=2048))

    assert len(pdf_pages) == 2
    assert len(tiff_pages) == 2
    assert max(Image.open(io.BytesIO(tiff_pages[0])).size) == 2048
